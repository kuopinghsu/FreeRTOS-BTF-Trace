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
  - STI software-trace events are scattered at random intervals.

Usage examples
--------------
  # defaults: 8 cores, 100 tasks, 1 M events  →  freertos_8c_100t_1m_events.btf
    python3 gen_trace.py

  # 4 cores, 50 tasks, 500 K events
    python3 gen_trace.py -c 4 -t 50 -e 500000 -o my_trace.btf

  # 16 cores, 200 tasks, 2 M events, 500 Hz tick, seed 7
    python3 gen_trace.py -c 16 -t 200 -e 2000000 --tick-hz 500 --seed 7

Options
-------
  -c / --cores            Number of CPU cores                (default: 8)
  -t / --tasks            Number of worker tasks             (default: 100)
  -e / --events           Target non-comment event lines     (default: 1_000_000)
  -o / --output           Output file path                   (default: auto)
  --tick-hz               RTOS tick frequency in Hz          (default: 1000)
  --freq-hz               CPU clock frequency in Hz          (default: 200_000_000)
  --sti-interval-us       Approx µs between STI tag events   (default: 30_000)
  --idle-prob             Probability a core goes IDLE [0–1] (default: 0.20)
  --max-burst-ticks       Max consecutive ticks a task runs  (default: 5)
  --seed                  Random seed                        (default: 42)
  --no-sti                Suppress all STI events
  --no-migration          Pin each task to one core
"""
import argparse
import heapq
import itertools
import random
import sys
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

# STI software instrumentation tag names
_STI_TAGS = [
    "ISR_Enter",    "ISR_Exit",     "Sem_Post",     "Sem_Wait",
    "Mutex_Lock",   "Mutex_Unlock", "Queue_Send",   "Queue_Recv",
    "Buf_Full",     "Buf_Empty",    "DMA_Done",     "DMA_Error",
    "Overrun",      "Underrun",     "Checkpoint",   "Assert_OK",
]

# Keywords that imply a high-priority task
_HIGH_PRIO_KW = {"CAN", "Safety", "Watchdog", "Brake", "Motor",
                 "PID", "Kalman", "Fusion", "Health", "ISR"}

def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate a synthetic FreeRTOS BTF trace file.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("-c", "--cores",   type=int, default=8,
                        help="Number of CPU cores")
    parser.add_argument("-t", "--tasks",   type=int, default=100,
                        help="Number of worker tasks")
    parser.add_argument("-e", "--events",  type=int, default=1_000_000,
                        help="Target non-comment event lines")
    parser.add_argument("-o", "--output",  type=str, default="",
                        help="Output BTF file (auto-generated name if omitted)")
    parser.add_argument("--tick-hz",       type=int, default=1_000,
                        help="RTOS tick frequency in Hz (1000 → 1 ms tick)")
    parser.add_argument("--freq-hz",       type=int, default=200_000_000,
                        help="CPU clock frequency in Hz")
    parser.add_argument("--sti-interval-us", type=int, default=30_000,
                        help="Approximate µs between STI tag events")
    parser.add_argument("--idle-prob",     type=float, default=0.20,
                        help="Probability [0–1] a core picks IDLE instead of a worker")
    parser.add_argument("--max-burst-ticks", type=int, default=5,
                        help="Maximum RTOS ticks a task runs before being preempted")
    parser.add_argument("--seed",          type=int, default=42,
                        help="Random seed for reproducibility")
    parser.add_argument("--no-sti",        action="store_true",
                        help="Suppress all STI software-trace events")
    parser.add_argument("--no-migration",  action="store_true",
                        help="Pin each task to one core (disable migration)")
    # Show full help when invoked with no arguments
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)
    return parser.parse_args()

def main():
    args = parse_args()

    # ── Validate ──────────────────────────────────────────────────────────────
    for flag, val in [("--cores", args.cores), ("--tasks", args.tasks),
                      ("--events", args.events), ("--tick-hz", args.tick_hz),
                      ("--max-burst-ticks", args.max_burst_ticks)]:
        if val < 1:
            sys.exit(f"error: {flag} must be >= 1")
    if not (0.0 <= args.idle_prob <= 1.0):
        sys.exit("error: --idle-prob must be between 0.0 and 1.0")

    random.seed(args.seed)

    num_cores        = args.cores
    num_workers      = args.tasks
    tick_us          = max(1, 1_000_000 // args.tick_hz)
    freq_hz          = args.freq_hz
    target_total     = args.events
    sti_interval_us  = args.sti_interval_us
    idle_prob        = args.idle_prob
    max_burst_ticks  = args.max_burst_ticks
    enable_sti       = not args.no_sti
    enable_migration = not args.no_migration

    # ── Build worker name list ────────────────────────────────────────────────
    # Cycle through the pool; append numeric suffix when names are exhausted.
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
            suffix_ctr[base] = suffix_ctr.get(base, 1) + 1
            name = f"{base}_{suffix_ctr[base]}"
            used.add(name)
            workers.append(name)

    worker_set = set(workers)

    # ── BTF identifiers ───────────────────────────────────────────────────────
    idle_names = [f"IDLE{c}" for c in range(num_cores)]
    tick_task  = "TICK"
    timer_service_name = "Tmr Svc"
    worker_id_by_name: dict[str, int] = {n: i + 9 for i, n in enumerate(workers)}
    timer_service_id = num_workers + 9

    # Task priorities: high-prio keywords → 7–10, others → 1–6
    def _task_priority(name: str) -> int:
        if any(k in name for k in _HIGH_PRIO_KW):
            return random.randint(7, 10)
        return random.randint(1, 6)
    worker_priority: dict[str, int] = {n: _task_priority(n) for n in workers}

    def format_task_label(core: int, task: str) -> str:
        if task in worker_set:
            return f"[{core}/{worker_id_by_name[task]}]{task}"
        if task == timer_service_name:
            return f"[{core}/{timer_service_id}]{task}"
        return task   # IDLE0…N and TICK are bare names

    # ── Output accumulator ────────────────────────────────────────────────────
    output_lines: list[str] = []
    event_count = 0

    def emit(line: str, *, comment: bool = False) -> None:
        nonlocal event_count
        output_lines.append(line)
        if not comment:
            event_count += 1

    # ── BTF header ────────────────────────────────────────────────────────────
    now_s = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    emit("#version 2.2.0",                comment=True)
    emit("#creator synthetic_trace_gen",  comment=True)
    emit(f"#creationDate {now_s}",        comment=True)
    emit("#timeScale us",                 comment=True)

    # ── Initialisation phase ──────────────────────────────────────────────────
    time_us = 405
    for core_idx in range(num_cores):
        emit(f"{time_us},Core_{core_idx},0,C,Core_{core_idx},0,set_frequency,{freq_hz}")
    time_us += 5 * num_cores

    for core_idx in range(num_cores):
        emit(f"{time_us},Core_{core_idx},0,T,{idle_names[core_idx]},0,preempt,task_create")
        time_us += 15

    emit(f"{time_us},Core_0,0,T,[0/{timer_service_id}]{timer_service_name},0,preempt,task_create")
    time_us += 25

    for core_idx in range(num_cores):
        emit(f"{time_us + core_idx * 10},{idle_names[core_idx]},0,T,{idle_names[core_idx]},0,resume,")
    time_us += num_cores * 10 + 50

    for name in workers:
        emit(f"{time_us},Core_0,0,T,[0/{worker_id_by_name[name]}]{name},0,preempt,task_create")
        time_us += 18

    # ── Simulation ────────────────────────────────────────────────────────────
    sim_start = time_us + 200

    core_task: list[str] = list(idle_names)   # each core starts on its IDLE task

    # Ready heap: (earliest_ready_time, task_name)
    ready_heap: list[tuple[int, str]] = [(sim_start, n) for n in workers]
    heapq.heapify(ready_heap)

    def pick_next(core: int, now: int) -> str:
        """
        Choose the next task for *core*.
        - With probability IDLE_PROB, return the core's IDLE task.
        - Otherwise pick the highest-priority task whose ready-time <= now.
        - If no task is ready, fall through to IDLE.
        """
        if random.random() < idle_prob:
            return idle_names[core]

        # Drain all tasks that are ready by now into a candidates list.
        candidates: list[str] = []
        while ready_heap and ready_heap[0][0] <= now:
            _, name = heapq.heappop(ready_heap)
            candidates.append(name)

        if not candidates:
            return idle_names[core]   # nothing ready yet → IDLE

        # Pick highest-priority candidate; return the rest immediately.
        best = max(candidates, key=lambda n: worker_priority[n])
        for n in candidates:
            if n != best:
                heapq.heappush(ready_heap, (now, n))
        return best

    def burst_us(task: str) -> int:
        """
        Run duration in µs.
        High-priority tasks: short bursts (1–2 ticks).
        Low-priority tasks:  up to MAX_BURST_TICKS ticks.
        """
        prio = worker_priority.get(task, 3)
        if prio >= 8:
            ticks = random.randint(1, 2)
        elif prio >= 5:
            ticks = random.randint(1, max(1, max_burst_ticks // 2))
        else:
            ticks = random.randint(1, max_burst_ticks)
        jitter = random.randint(-(tick_us // 10), tick_us // 10)
        return max(50, ticks * tick_us + jitter)

    def block_us(task: str) -> int:
        """
        How long the task blocks after its burst (0 = immediately re-queued).
        Low-priority tasks sleep longer, creating more IDLE time.
        """
        prio = worker_priority.get(task, 3)
        max_sleep_ticks = max(0, 8 - prio)
        sleep_ticks = random.randint(0, max_sleep_ticks)
        return sleep_ticks * tick_us + random.randint(0, tick_us // 4)

    # Per-core scheduling heap: (next_switch_time, core_index)
    sched_heap: list[tuple[int, int]] = [
        (sim_start + core_idx * (max(1, tick_us // num_cores)), core_idx)
        for core_idx in range(num_cores)
    ]
    heapq.heapify(sched_heap)

    tick_no   = 0
    next_tick = sim_start + tick_us
    sti_no    = 0
    next_sti  = sim_start + random.randint(tick_us, sti_interval_us)

    core_preempt_prob = 0.45   # timer-interrupt vs. voluntary yield

    while event_count < target_total:
        if not sched_heap:
            break
        cur_t, core = heapq.heappop(sched_heap)

        # ── TICK ISR (fire every tick that elapsed up to cur_t) ───────────
        while next_tick <= cur_t and event_count < target_total:
            emit(f"{next_tick},{tick_task},0,T,{tick_task},0,resume,tick_{tick_no}")
            emit(f"{next_tick + 1},{tick_task},0,T,{tick_task},0,preempt,")
            tick_no  += 1
            next_tick += tick_us

        # ── STI software-trace event ──────────────────────────────────────
        if enable_sti and next_sti <= cur_t and event_count < target_total:
            tag = random.choice(_STI_TAGS)
            emit(f"{next_sti},Core_{core},0,STI,{tag},0,trigger,{tag}")
            sti_no  += 1
            next_sti = cur_t + random.randint(
                sti_interval_us // 2, sti_interval_us * 2)

        if event_count >= target_total:
            break

        old_task = core_task[core]
        old_label  = format_task_label(core, old_task)

        new_task = pick_next(core, cur_t)

        # --no-migration: tasks stay on the same core (hash-pinned)
        if not enable_migration and new_task in worker_set:
            if hash(new_task) % num_cores != core:
                heapq.heappush(ready_heap, (cur_t, new_task))
                new_task = idle_names[core]

        new_label = format_task_label(core, new_task)

        # Return old worker to the ready heap after its blocking period
        if old_task in worker_set:
            heapq.heappush(ready_heap, (cur_t + block_us(old_task), old_task))

        # ── Context switch ────────────────────────────────────────────────
        if old_task == new_task:
            # Same task keeps running – no switch event, just reschedule
            idle_slice = random.randint(TICK_US // 8, TICK_US // 2)
            heapq.heappush(sched_heap, (cur_t + idle_slice, core))
            continue

        if random.random() < core_preempt_prob:
            # Timer interrupt preempts the running task
            emit(f"{cur_t},Core_{core},0,T,{old_label},0,preempt,")
            emit(f"{cur_t},{old_label},0,T,{new_label},0,resume,")
        else:
            # Task yields voluntarily (vTaskDelay, semaphore wait, …)
            emit(f"{cur_t},{old_label},0,T,{old_label},0,preempt,")
            emit(f"{cur_t},{old_label},0,T,{new_label},0,resume,")

        core_task[core] = new_task

        # Schedule the next switch on this core
        if new_task in worker_set:
            next_burst = burst_us(new_task)
        else:
            # IDLE: run until next TICK boundary (roughly)
            next_burst = random.randint(tick_us // 8, tick_us)

        heapq.heappush(sched_heap, (cur_t + next_burst, core))

    # ── Write output ──────────────────────────────────────────────────────────
    if args.output:
        out_path = args.output
    else:
        e_str = (f"{target_total // 1_000}k"
             if target_total < 1_000_000
             else f"{target_total // 1_000_000}m")
        out_path = f"freertos_{num_cores}c_{num_workers}t_{e_str}_events.btf"

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(output_lines))
        fh.write("\n")

    sim_dur_ms = (next_tick - sim_start) / 1_000
    print(
        f"Done: {event_count:>10,} events  |  "
        f"{tick_no:>6,} ticks ({tick_us} µs/tick)  |  "
        f"{sti_no:>5,} STI  |  "
        f"sim duration ≈ {sim_dur_ms:,.1f} ms  →  {out_path}"
    )

if __name__ == "__main__":
    main()
