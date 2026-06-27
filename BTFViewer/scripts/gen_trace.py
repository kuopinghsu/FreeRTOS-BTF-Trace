#!/usr/bin/env python3
"""
Generate a synthetic FreeRTOS-style BTF trace.

Task names reflect a realistic embedded system:
  CAN_Rx, CAN_Tx, UART_Logger, Accel_Read, Motor_L, PID_Speed, …

Scheduling behaviour
--------------------
  - Tasks have priorities; high-priority tasks run short bursts (1–2 ticks),
    low-priority tasks may run for up to --max-burst-ticks ticks.
  - After each burst a task blocks for 0–8 ticks before re-entering the
    ready queue, giving every core genuine IDLE time slots.
  - The same task migrates to a different core at each scheduling decision.
  - TICK fires every TICK_US µs (default 1 ms).
  - STI software-trace events include generic tags, interval_start/stop pairs,
    and mutex create/take/give sequences (firmware-style channels).

Usage examples
--------------
  # defaults: 4 cores, 100 tasks, 8 K events  →  freertos_4c_100t_8k_events.btf
    python3 scripts/gen_trace.py

  # 4 cores, 50 tasks, 500 K events
    python3 scripts/gen_trace.py -c 4 -t 50 -e 500000 -o my_trace.btf

  # 16 cores, 200 tasks, 2 M events, 500 Hz tick
    python3 scripts/gen_trace.py -c 16 -t 200 -e 2000000 --tick-hz 500

Options
-------
  -c / --cores            Number of CPU cores                (default: DEFAULT_CORES)
  -t / --tasks            Number of worker tasks             (default: DEFAULT_TASKS)
  -e / --events           Target non-comment event lines     (default: DEFAULT_EVENTS)
  -o / --output           Output file path                   (default: auto)
  --tick-hz               RTOS tick frequency in Hz          (default: DEFAULT_TICK_HZ)
  --freq-hz               CPU clock frequency in Hz          (default: DEFAULT_FREQ_HZ)
  --sti-interval-us       Approx µs between generic STI tags (default: DEFAULT_STI_INTERVAL_US)
  --interval-ids          Number of distinct interval IDs      (default: DEFAULT_INTERVAL_IDS)
  --mutex-count           Number of mutex objects to create  (default: DEFAULT_MUTEX_COUNT)
  --idle-prob             Probability a core goes IDLE [0–1] (default: DEFAULT_IDLE_PROB)
  --max-burst-ticks       Max consecutive ticks a task runs  (default: DEFAULT_MAX_BURST_TICKS)
  --no-sti                Suppress all STI events
  --no-intervals          Suppress interval_start / interval_stop STI
  --no-mutex-sti          Suppress mutex create / take / give STI
  --no-migration          Pin each task to one core
"""
from __future__ import annotations

import argparse
import heapq
import itertools
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Meaningful task-name pool (embedded RTOS domain)
# ---------------------------------------------------------------------------
_TASK_NAME_POOL = [
    # Communication
    "CAN_Rx",       "CAN_Tx",       "UART_Logger",  "SPI_Flash",
    "I2C_Sensor",   "ETH_Recv",     "ETH_Send",     "USB_CDC",
    "BLE_Adv",      "BLE_Conn",     "Lin_Rx",       "Lin_Tx",
    # Sensor processing
    "Accel_Read",   "Gyro_Read",    "Magneto_Read", "Baro_Read",
    "Temp_Read",    "Lidar_Scan",   "Camera_Cap",   "ADC_Sample",
    # Motor / actuator
    "Motor_L",      "Motor_R",      "Servo_Ctrl",   "Pump_Ctrl",
    "Brake_Ctrl",   "Steer_Ctrl",   "Fan_Ctrl",     "LED_Strip",
    # Control algorithms
    "PID_Speed",    "PID_Angle",    "PID_Pos",      "Kalman_IMU",
    "Fusion_AHRS",  "Nav_Planner",  "Path_Follow",  "Obstacle_Det",
    # System / housekeeping
    "Safety_Mon",   "Watchdog",     "Health_Chk",   "Diag_Report",
    "HMI_Update",   "LCD_Draw",     "Event_Log",    "Config_Save",
    "Flash_Wear",   "Power_Mgr",    "Bat_Monitor",  "Thermal_Ctrl",
    # Networking / middleware
    "MQTT_Pub",     "MQTT_Sub",     "HTTP_Client",  "TLS_Worker",
    "DNS_Resolve",  "NTP_Sync",     "OTA_Update",   "File_Sys",
    # Application
    "App_State",    "App_Cmd",      "App_Sched",    "App_Log",
    "UI_Touch",     "UI_Gesture",   "Audio_Record", "Audio_Play",
    "Video_Enc",    "Video_Dec",    "DSP_Filter",   "FFT_Worker",
    "ML_Infer",     "Crypto_Hash",  "Crypto_Sign",  "RNG_Fill",
    "Mem_Compact",  "GC_Worker",    "Trace_Flush",  "Perf_Counter",
    # Overflow names (support --tasks > 80)
    "Task_Alpha",   "Task_Beta",    "Task_Gamma",   "Task_Delta",
    "Task_Epsilon", "Task_Zeta",    "Task_Eta",     "Task_Theta",
    "Task_Iota",    "Task_Kappa",   "Task_Lambda",  "Task_Mu",
    "Task_Nu",      "Task_Xi",      "Task_Omicron", "Task_Pi",
    "Task_Rho",     "Task_Sigma",   "Task_Tau",     "Task_Upsilon",
    "Worker_A",     "Worker_B",     "Worker_C",     "Worker_D",
    "Worker_E",     "Worker_F",     "Worker_G",     "Worker_H",
    "Worker_I",     "Worker_J",     "Worker_K",     "Worker_L",
    "Worker_M",     "Worker_N",     "Worker_O",     "Worker_P",
    "Svc_1",        "Svc_2",        "Svc_3",        "Svc_4",
    "Svc_5",        "Svc_6",        "Svc_7",        "Svc_8",
]

# Generic STI software instrumentation tag names (legacy / ad-hoc channels)
_STI_TAGS = [
    "ISR_Enter",    "ISR_Exit",     "Sem_Post",     "Sem_Wait",
    "Mutex_Lock",   "Mutex_Unlock", "Queue_Send",   "Queue_Recv",
    "Buf_Full",     "Buf_Empty",    "DMA_Done",     "DMA_Error",
    "Overrun",      "Underrun",     "Checkpoint",   "Assert_OK",
]

# Keywords that imply a high-priority task
_HIGH_PRIO_KW = {"CAN", "Safety", "Watchdog", "Brake", "Motor",
                 "PID", "Kalman", "Fusion", "Health", "ISR"}

# ---------------------------------------------------------------------------
# Default settings — edit these to change the defaults without touching
# the argument parser below.
# ---------------------------------------------------------------------------
DEFAULT_CORES           = 4
DEFAULT_TASKS           = 100
DEFAULT_EVENTS          = 8_000
DEFAULT_TICK_HZ         = 1_000
DEFAULT_FREQ_HZ         = 100_000_000
DEFAULT_STI_INTERVAL_US = 30_000
DEFAULT_INTERVAL_IDS    = 3
DEFAULT_MUTEX_COUNT     = 2
DEFAULT_IDLE_PROB       = 0.20
DEFAULT_MAX_BURST_TICKS = 5
MUTEX_PTR_BASE          = 0x80010000

def _interval_note(interval_id: int, task_id: int | None, *, use_tid: bool) -> str:
    if use_tid and task_id is not None:
        return f"{interval_id} tid:{task_id}"
    return str(interval_id)

class _IntervalScenario:
    """Emit paired interval_start / interval_stop STI events per task burst."""

    def __init__(self, num_ids: int, *, start_prob: float = 0.45) -> None:
        self._num_ids = max(1, num_ids)
        self._start_prob = start_prob
        self._open: dict[str, list[str]] = defaultdict(list)

    def on_task_start(
        self,
        buf: list[str],
        core_name: str,
        task: str,
        task_id: int,
        t: int,
        rndf,
        rndi,
    ) -> int:
        if rndf() >= self._start_prob:
            return 0
        iid = rndi(0, self._num_ids - 1)
        use_tid = rndf() < 0.65
        note = _interval_note(iid, task_id, use_tid=use_tid)
        buf.append(f"{t},{core_name},0,STI,interval_start,0,trigger,{note}\n")
        self._open[task].append(note)
        return 1

    def on_task_stop(self, buf: list[str], core_name: str, task: str, t: int) -> int:
        stack = self._open.get(task)
        if not stack:
            return 0
        note = stack.pop()
        buf.append(f"{t},{core_name},0,STI,interval_stop,0,trigger,{note}\n")
        if not stack:
            del self._open[task]
        return 1

class _MutexScenario:
    """Emit firmware-style mutex STI: create / take / give with object pointers."""

    def __init__(self, ptrs: list[str], *, take_prob: float = 0.30) -> None:
        self._ptrs = ptrs
        self._take_prob = take_prob
        self._held: dict[str, list[str]] = defaultdict(list)

    def emit_creates(self, buf: list[str], core_name: str, t: int) -> int:
        n = 0
        for ptr in self._ptrs:
            buf.append(f"{t},{core_name},0,STI,mutex,0,trigger,create {ptr}\n")
            n += 1
            t += 2
        return n

    def on_task_start(
        self,
        buf: list[str],
        core_name: str,
        task: str,
        t: int,
        rndf,
        rndch,
    ) -> int:
        if not self._ptrs or rndf() >= self._take_prob:
            return 0
        held = self._held[task]
        available = [p for p in self._ptrs if p not in held]
        if not available:
            return 0
        ptr = rndch(available)
        buf.append(f"{t},{core_name},0,STI,mutex,0,trigger,take {ptr}\n")
        held.append(ptr)
        return 1

    def on_task_stop(self, buf: list[str], core_name: str, task: str, t: int) -> int:
        held = self._held.get(task)
        if not held:
            return 0
        n = 0
        while held:
            ptr = held.pop()
            buf.append(f"{t},{core_name},0,STI,mutex,0,trigger,give {ptr}\n")
            n += 1
            t += 1
        del self._held[task]
        return n

def parse_args():
    """Parse and return command-line arguments for trace generation."""
    parser = argparse.ArgumentParser(
        description="Generate a synthetic FreeRTOS BTF trace file.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("-c", "--cores",   type=int, default=DEFAULT_CORES,
                        help="Number of CPU cores")
    parser.add_argument("-t", "--tasks",   type=int, default=DEFAULT_TASKS,
                        help="Number of worker tasks")
    parser.add_argument("-e", "--events",  type=int, default=DEFAULT_EVENTS,
                        help="Target non-comment event lines")
    parser.add_argument("-o", "--output",  type=str, default="",
                        help="Output BTF file (auto-generated name if omitted)")
    parser.add_argument("--tick-hz",       type=int, default=DEFAULT_TICK_HZ,
                        help="RTOS tick frequency in Hz (1000 → 1 ms tick)")
    parser.add_argument("--freq-hz",       type=int, default=DEFAULT_FREQ_HZ,
                        help="CPU clock frequency in Hz")
    parser.add_argument("--sti-interval-us", type=int, default=DEFAULT_STI_INTERVAL_US,
                        help="Approximate µs between generic STI tag events")
    parser.add_argument("--interval-ids",  type=int, default=DEFAULT_INTERVAL_IDS,
                        help="Number of distinct interval IDs (0 … N-1)")
    parser.add_argument("--mutex-count",   type=int, default=DEFAULT_MUTEX_COUNT,
                        help="Number of mutex objects (create/take/give STI)")
    parser.add_argument("--idle-prob",     type=float, default=DEFAULT_IDLE_PROB,
                        help="Probability [0–1] a core picks IDLE instead of a worker")
    parser.add_argument("--max-burst-ticks", type=int, default=DEFAULT_MAX_BURST_TICKS,
                        help="Maximum RTOS ticks a task runs before being preempted")
    parser.add_argument("--no-sti",        action="store_true",
                        help="Suppress all STI software-trace events")
    parser.add_argument("--no-intervals",  action="store_true",
                        help="Suppress interval_start / interval_stop STI events")
    parser.add_argument("--no-mutex-sti",  action="store_true",
                        help="Suppress mutex create / take / give STI events")
    parser.add_argument("--no-migration",  action="store_true",
                        help="Pin each task to one core (disable migration)")
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)
    return parser.parse_args()

def main():
    """Entry point: parse arguments, generate and write synthetic BTF trace."""
    args = parse_args()

    for flag, val in [("--cores", args.cores), ("--tasks", args.tasks),
                      ("--events", args.events), ("--tick-hz", args.tick_hz),
                      ("--max-burst-ticks", args.max_burst_ticks),
                      ("--interval-ids", args.interval_ids),
                      ("--mutex-count", args.mutex_count)]:
        if val < 1:
            sys.exit(f"error: {flag} must be >= 1")
    if not (0.0 <= args.idle_prob <= 1.0):
        sys.exit("error: --idle-prob must be between 0.0 and 1.0")

    num_cores        = args.cores
    num_workers      = args.tasks
    tick_us          = max(1, 1_000_000 // args.tick_hz)
    freq_hz          = args.freq_hz
    target_total     = args.events
    sti_interval_us  = args.sti_interval_us
    idle_prob        = args.idle_prob
    max_burst_ticks  = args.max_burst_ticks
    enable_sti       = not args.no_sti
    enable_intervals = enable_sti and not args.no_intervals
    enable_mutex_sti = enable_sti and not args.no_mutex_sti
    enable_migration = not args.no_migration

    pool = _TASK_NAME_POOL[:]
    random.shuffle(pool)
    workers: list[str] = []
    used: set[str] = set()
    suffix_ctr: dict[str, int] = {}
    for base in itertools.islice(itertools.cycle(pool), num_workers):
        if base not in used:
            used.add(base)
            workers.append(base)
        else:
            suffix_ctr[base] = suffix_ctr.get(base, 0) + 1
            name = f"{base}_{suffix_ctr[base]}"
            used.add(name)
            workers.append(name)

    worker_set = set(workers)

    idle_names = [f"IDLE{c}" for c in range(num_cores)]
    tick_task  = "TICK"
    timer_service_name = "Tmr Svc"
    worker_id_by_name: dict[str, int] = {n: i + 9 for i, n in enumerate(workers)}
    timer_service_id = num_workers + 9

    def _task_priority(name: str) -> int:
        if any(k in name for k in _HIGH_PRIO_KW):
            return random.randint(7, 10)
        return random.randint(1, 6)

    worker_priority: dict[str, int] = {n: _task_priority(n) for n in workers}

    core_names = [f"Core_{c}" for c in range(num_cores)]
    label_map: dict[tuple[int, str], str] = {}
    for _c in range(num_cores):
        for _n in workers:
            label_map[(_c, _n)] = f"[{_c}/{worker_id_by_name[_n]}]{_n}"
        label_map[(_c, timer_service_name)] = (
            f"[{_c}/{timer_service_id}]{timer_service_name}")
        label_map[(_c, idle_names[_c])] = idle_names[_c]

    if args.output:
        out_path = args.output
    else:
        _e_str = (f"{target_total // 1_000}k"
                  if target_total < 1_000_000
                  else f"{target_total // 1_000_000}m")
        out_path = (f"freertos_{num_cores}c_{num_workers}t"
                    f"_{_e_str}_events.btf")

    mutex_ptrs = [
        f"0x{MUTEX_PTR_BASE + i * 0x100:08x}"
        for i in range(args.mutex_count)
    ]
    interval_scenario = _IntervalScenario(args.interval_ids)
    mutex_scenario = _MutexScenario(mutex_ptrs)

    _FLUSH_EVERY = 100_000
    _buf: list[str] = []
    event_count = 0
    _fh = open(out_path, "w", encoding="utf-8", buffering=1 << 20)  # noqa: SIM115

    def _flush_buf() -> None:
        _fh.writelines(_buf)
        _buf.clear()

    def emit(line: str, *, comment: bool = False) -> None:
        nonlocal event_count
        _buf.append(line + "\n")
        if not comment:
            event_count += 1
        if len(_buf) >= _FLUSH_EVERY:
            _flush_buf()

    def _count_buf(n: int) -> None:
        nonlocal event_count
        event_count += n
        if len(_buf) >= _FLUSH_EVERY:
            _flush_buf()

    now_s = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    emit("#version 2.2.0",                comment=True)
    emit("#creator synthetic_trace_gen",  comment=True)
    emit(f"#creationDate {now_s}",        comment=True)
    emit("#timeScale us",                 comment=True)

    time_us = 405
    for core_idx in range(num_cores):
        emit(f"{time_us},Core_{core_idx},0,C,Core_{core_idx},0,set_frequency,{freq_hz}")
    time_us += 5 * num_cores

    for core_idx in range(num_cores):
        emit(f"{time_us},Core_{core_idx},0,T,{idle_names[core_idx]},0,preempt,task_create")
        time_us += 15

    emit(f"{time_us},Core_0,0,T,[0/{timer_service_id}]{timer_service_name},0,preempt,task_create")
    time_us += 25

    for name in workers:
        emit(f"{time_us},Core_0,0,T,[0/{worker_id_by_name[name]}]{name},0,preempt,task_create")
        time_us += 18

    init_core_tasks = [workers[i % len(workers)] for i in range(num_cores)]

    for core_idx, first_task in enumerate(init_core_tasks):
        task_label = label_map[(core_idx, first_task)]
        emit(f"{time_us},{core_names[core_idx]},0,T,{task_label},0,resume,")
        time_us += 5

    if enable_mutex_sti and mutex_ptrs:
        n = mutex_scenario.emit_creates(_buf, core_names[0], time_us)
        _count_buf(n)
        time_us += n * 2 + 10

    if enable_intervals:
        _buf.append(f"{time_us},{core_names[0]},0,STI,interval_start,0,trigger,0\n")
        _count_buf(1)
        time_us += 20

    sim_start = time_us + 50
    core_task: list[str] = list(init_core_tasks)

    pending_heap: list[tuple[int, str]] = []
    ready_list: list[str] = [w for w in workers if w not in set(init_core_tasks)]

    _xs = [random.getrandbits(32) or 0xDEADBEEF]

    def _rndf() -> float:
        x = _xs[0]; x ^= (x << 13) & 0xFFFFFFFF; x ^= x >> 17; x ^= (x << 5) & 0xFFFFFFFF
        _xs[0] = x
        return x * 2.3283064365e-10

    def _rndi(a: int, b: int) -> int:
        x = _xs[0]; x ^= (x << 13) & 0xFFFFFFFF; x ^= x >> 17; x ^= (x << 5) & 0xFFFFFFFF
        _xs[0] = x
        return a + x % (b - a + 1)

    def _rndch(seq):
        x = _xs[0]; x ^= (x << 13) & 0xFFFFFFFF; x ^= x >> 17; x ^= (x << 5) & 0xFFFFFFFF
        _xs[0] = x
        return seq[x % len(seq)]

    _pick_ctr = 0

    def pick_next(core: int, now: int) -> str:
        nonlocal _pick_ctr
        if _rndf() < idle_prob:
            return idle_names[core]

        while pending_heap and pending_heap[0][0] <= now:
            _, name = heapq.heappop(pending_heap)
            ready_list.append(name)

        if ready_list:
            idx  = _pick_ctr % len(ready_list)
            _pick_ctr += 1
            last = len(ready_list) - 1
            ready_list[idx], ready_list[last] = ready_list[last], ready_list[idx]
            return ready_list.pop()
        return idle_names[core]

    def burst_us(task: str) -> int:
        prio = worker_priority.get(task, 3)
        if prio >= 8:
            ticks = _rndi(1, 2)
        elif prio >= 5:
            ticks = _rndi(1, max(1, max_burst_ticks // 2))
        else:
            ticks = _rndi(1, max_burst_ticks)
        jitter = _rndi(-(tick_us // 10), tick_us // 10)
        return max(50, ticks * tick_us + jitter)

    def block_us(task: str) -> int:
        prio = worker_priority.get(task, 3)
        max_sleep_ticks = max(0, 8 - prio)
        sleep_ticks = _rndi(0, max_sleep_ticks)
        return sleep_ticks * tick_us + _rndi(0, tick_us // 4)

    sched_heap: list[tuple[int, int]] = [
        (sim_start + core_idx * (max(1, tick_us // num_cores)), core_idx)
        for core_idx in range(num_cores)
    ]
    heapq.heapify(sched_heap)

    tick_no      = 0
    next_tick    = sim_start + tick_us
    sti_no       = 0
    interval_no  = 0
    mutex_no     = 0
    next_sti     = sim_start + _rndi(tick_us, sti_interval_us)
    core_preempt_prob = 0.45

    try:
        while event_count < target_total:
            if not sched_heap:
                break
            cur_t, core = heapq.heappop(sched_heap)

            while event_count < target_total:
                tick_due = next_tick <= cur_t
                sti_due  = enable_sti and next_sti <= cur_t
                if not tick_due and not sti_due:
                    break
                if tick_due and (not sti_due or next_tick <= next_sti):
                    _buf.append(f"{next_tick},{tick_task},0,T,{tick_task},0,resume,{tick_no}\n")
                    _buf.append(f"{next_tick + 1},{tick_task},0,T,{tick_task},0,preempt,\n")
                    event_count += 2
                    tick_no  += 1
                    next_tick += tick_us
                else:
                    tag = _rndch(_STI_TAGS)
                    _buf.append(f"{next_sti},{core_names[core]},0,STI,{tag},0,trigger,{tag}\n")
                    event_count += 1
                    sti_no  += 1
                    next_sti = cur_t + _rndi(sti_interval_us // 2, sti_interval_us * 2)
                if len(_buf) >= _FLUSH_EVERY:
                    _flush_buf()

            if event_count >= target_total:
                break

            old_task  = core_task[core]
            old_label = label_map.get((core, old_task), old_task)
            new_task  = pick_next(core, cur_t)

            if not enable_migration and new_task in worker_set:
                if hash(new_task) % num_cores != core:
                    ready_list.append(new_task)
                    new_task = idle_names[core]

            new_label = label_map.get((core, new_task), new_task)

            if old_task in worker_set:
                _bl = block_us(old_task)
                if _bl == 0:
                    ready_list.append(old_task)
                else:
                    heapq.heappush(pending_heap, (cur_t + _bl, old_task))

            if old_task == new_task:
                idle_slice = _rndi(tick_us // 8, tick_us // 2)
                heapq.heappush(sched_heap, (cur_t + idle_slice, core))
                if len(_buf) >= _FLUSH_EVERY:
                    _flush_buf()
                continue

            if old_task in worker_set:
                if enable_intervals:
                    n = interval_scenario.on_task_stop(
                        _buf, core_names[core], old_task, cur_t)
                    interval_no += n
                    event_count += n
                if enable_mutex_sti:
                    n = mutex_scenario.on_task_stop(
                        _buf, core_names[core], old_task, cur_t)
                    mutex_no += n
                    event_count += n

            if _rndf() < core_preempt_prob:
                _buf.append(f"{cur_t},{core_names[core]},0,T,{old_label},0,preempt,\n")
                _buf.append(f"{cur_t},{old_label},0,T,{new_label},0,resume,\n")
            else:
                _buf.append(f"{cur_t},{old_label},0,T,{old_label},0,preempt,\n")
                _buf.append(f"{cur_t},{old_label},0,T,{new_label},0,resume,\n")
            event_count += 2

            core_task[core] = new_task

            if new_task in worker_set:
                if enable_intervals:
                    n = interval_scenario.on_task_start(
                        _buf, core_names[core], new_task,
                        worker_id_by_name[new_task], cur_t, _rndf, _rndi)
                    interval_no += n
                    event_count += n
                if enable_mutex_sti:
                    n = mutex_scenario.on_task_start(
                        _buf, core_names[core], new_task, cur_t, _rndf, _rndch)
                    mutex_no += n
                    event_count += n

            if len(_buf) >= _FLUSH_EVERY:
                _flush_buf()

            if new_task in worker_set:
                next_burst = burst_us(new_task)
            else:
                next_burst = _rndi(tick_us // 8, tick_us)

            heapq.heappush(sched_heap, (cur_t + next_burst, core))

    finally:
        _flush_buf()
        _fh.close()

    sim_dur_ms = (next_tick - sim_start) / 1_000
    print(
        f"Done: {event_count:>10,} events  |  "
        f"{tick_no:>6,} ticks ({tick_us} µs/tick)  |  "
        f"{sti_no:>5,} generic STI  |  "
        f"{interval_no:>5,} interval STI  |  "
        f"{mutex_no:>5,} mutex STI  |  "
        f"sim duration ≈ {sim_dur_ms:,.1f} ms  →  {out_path}"
    )

if __name__ == "__main__":
    main()
