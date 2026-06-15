;; timeline_accel.wat – hot-path helpers for timeline pan/zoom (bisect, row cull, LOD reduce).
(module
  (memory (export "memory") 16)

  ;; ---- bisect_left: first i where arr[i] >= val --------------------------------
  (func $bisect_left (param $ptr i32) (param $len i32) (param $val f64) (result i32)
    (local $lo i32) (local $hi i32) (local $mid i32)
    (local.set $lo (i32.const 0))
    (local.set $hi (local.get $len))
    (block $done
      (loop $loop
        (br_if $done (i32.eq (local.get $lo) (local.get $hi)))
        (local.set $mid (i32.shr_u (i32.add (local.get $lo) (local.get $hi)) (i32.const 1)))
        (if (f64.lt
              (f64.load (i32.add (local.get $ptr) (i32.shl (local.get $mid) (i32.const 3))))
              (local.get $val))
          (then (local.set $lo (i32.add (local.get $mid) (i32.const 1))))
          (else (local.set $hi (local.get $mid))))
        (br $loop)
      )
    )
    (local.get $lo)
  )

  ;; ---- bisect_right: first i where arr[i] > val --------------------------------
  (func $bisect_right (param $ptr i32) (param $len i32) (param $val f64) (result i32)
    (local $lo i32) (local $hi i32) (local $mid i32)
    (local.set $lo (i32.const 0))
    (local.set $hi (local.get $len))
    (block $done
      (loop $loop
        (br_if $done (i32.eq (local.get $lo) (local.get $hi)))
        (local.set $mid (i32.shr_u (i32.add (local.get $lo) (local.get $hi)) (i32.const 1)))
        (if (f64.le
              (f64.load (i32.add (local.get $ptr) (i32.shl (local.get $mid) (i32.const 3))))
              (local.get $val))
          (then (local.set $lo (i32.add (local.get $mid) (i32.const 1))))
          (else (local.set $hi (local.get $mid))))
        (br $loop)
      )
    )
    (local.get $lo)
  )

  ;; visible_seg_range: write [from, hi] i32 pair at out_ptr
  (func (export "visible_seg_range")
    (param $starts i32) (param $len i32) (param $ns_lo f64) (param $ns_hi f64) (param $out i32)
    (local $lo i32) (local $hi i32) (local $from i32)
    (local.set $lo (call $bisect_left (local.get $starts) (local.get $len) (local.get $ns_lo)))
    (local.set $hi (call $bisect_right (local.get $starts) (local.get $len) (local.get $ns_hi)))
    (local.set $from (if (result i32) (i32.eqz (local.get $lo)) (then (i32.const 0)) (else (i32.sub (local.get $lo) (i32.const 1)))))
    (i32.store (local.get $out) (local.get $from))
    (i32.store (i32.add (local.get $out) (i32.const 4)) (local.get $hi))
  )

  ;; visible_row_range: ys/heights f64 arrays, write [i0, i1] at out_ptr
  (func (export "visible_row_range")
    (param $ys i32) (param $heights i32) (param $len i32)
    (param $scroll_y f64) (param $body_h f64) (param $buffer i32) (param $out i32)
    (local $vis_top f64) (local $vis_bot f64)
    (local $i0 i32) (local $i1 i32) (local $lo i32) (local $hi i32) (local $mid i32)
    (local $y f64) (local $h f64) (local $n i32)

    (local.set $vis_top (local.get $scroll_y))
    (local.set $vis_bot (f64.add (local.get $scroll_y) (local.get $body_h)))

    ;; i0 = first row with y + h > vis_top
    (local.set $lo (i32.const 0))
    (local.set $hi (local.get $len))
    (block $done0
      (loop $loop0
        (br_if $done0 (i32.eq (local.get $lo) (local.get $hi)))
        (local.set $mid (i32.shr_u (i32.add (local.get $lo) (local.get $hi)) (i32.const 1)))
        (local.set $y (f64.load (i32.add (local.get $ys) (i32.shl (local.get $mid) (i32.const 3)))))
        (local.set $h (f64.load (i32.add (local.get $heights) (i32.shl (local.get $mid) (i32.const 3)))))
        (if (f64.le (f64.add (local.get $y) (local.get $h)) (local.get $vis_top))
          (then (local.set $lo (i32.add (local.get $mid) (i32.const 1))))
          (else (local.set $hi (local.get $mid))))
        (br $loop0)
      )
    )
    (local.set $i0
      (if (result i32) (i32.lt_u (local.get $buffer) (local.get $lo))
        (then (i32.sub (local.get $lo) (local.get $buffer)))
        (else (i32.const 0))))

    ;; i1 = first row with y > vis_bot, then + buffer
    (local.set $lo (local.get $i0))
    (local.set $hi (local.get $len))
    (block $done1
      (loop $loop1
        (br_if $done1 (i32.eq (local.get $lo) (local.get $hi)))
        (local.set $mid (i32.shr_u (i32.add (local.get $lo) (local.get $hi)) (i32.const 1)))
        (local.set $y (f64.load (i32.add (local.get $ys) (i32.shl (local.get $mid) (i32.const 3)))))
        (if (f64.le (local.get $y) (local.get $vis_bot))
          (then (local.set $lo (i32.add (local.get $mid) (i32.const 1))))
          (else (local.set $hi (local.get $mid))))
        (br $loop1)
      )
    )
    (local.set $i1 (i32.add (local.get $lo) (local.get $buffer)))
    (local.set $n (local.get $len))
    (if (i32.gt_u (local.get $i1) (local.get $n)) (then (local.set $i1 (local.get $n))))

    (i32.store (local.get $out) (local.get $i0))
    (i32.store (i32.add (local.get $out) (i32.const 4)) (local.get $i1))
  )

  ;; lod_reduce: write segment indices [from..to] into out_ptr, return count
  (func (export "lod_reduce")
    (param $starts i32) (param $ends i32) (param $from i32) (param $to i32)
    (param $time_start f64) (param $ns_per_px f64) (param $max_out i32) (param $out i32)
    (result i32)
    (local $i i32) (local $count i32) (local $prev_px i64) (local $px i64)
    (local $s f64) (local $e f64) (local $last_idx i32)

    (local.set $count (i32.const 0))
    (local.set $prev_px (i64.const -2))
    (local.set $i (local.get $from))

    (block $break
      (loop $loop
        (br_if $break (i32.gt_u (local.get $i) (local.get $to)))
        (br_if $break (i32.ge_u (local.get $count) (local.get $max_out)))

        (local.set $s (f64.load (i32.add (local.get $starts) (i32.shl (local.get $i) (i32.const 3)))))
        (local.set $e (f64.load (i32.add (local.get $ends) (i32.shl (local.get $i) (i32.const 3)))))

        (local.set $px (if (result i64)
          (f64.lt (local.get $s) (local.get $time_start))
          (then (i64.const 0))
          (else (i64.trunc_f64_s (f64.floor (f64.div (f64.sub (local.get $s) (local.get $time_start)) (local.get $ns_per_px)))))))

        (if (i64.ne (local.get $px) (local.get $prev_px))
          (then
            (i32.store (i32.add (local.get $out) (i32.shl (local.get $count) (i32.const 2))) (local.get $i))
            (local.set $count (i32.add (local.get $count) (i32.const 1)))
            (local.set $prev_px (local.get $px))
            (local.set $last_idx (local.get $i))
          )
          (else
            (if (f64.gt (local.get $e)
                  (f64.load (i32.add (local.get $ends) (i32.shl (local.get $last_idx) (i32.const 3)))))
              (then
                (i32.store
                  (i32.add (local.get $out) (i32.shl (i32.sub (local.get $count) (i32.const 1)) (i32.const 2)))
                  (local.get $i))
                (local.set $last_idx (local.get $i))
              )
            )
          )
        )

        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $loop)
      )
    )
    (local.get $count)
  )
)
