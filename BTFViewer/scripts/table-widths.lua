-- Pandoc Lua filter: give PDF tables usable column widths.
--
-- Pipe-table dash rulers become LaTeX p{…} fractions. A first column marked
-- `| --- |` is ~2% of \linewidth, so "14", "1. Triage", or
-- `summarize_investigation_context` overprints the next column. Size columns
-- from cell text instead (LaTeX writer only).

local MIN_COL = 0.08
local MIN_FIRST = 0.10
local MAX_FIRST = 0.42

local function scan_rows(rows, j, maxlen)
  if not rows then
    return maxlen
  end
  for _, row in ipairs(rows) do
    local cell = row.cells and row.cells[j]
    if cell then
      local n = utf8.len(pandoc.utils.stringify(cell)) or 0
      if n > maxlen then
        maxlen = n
      end
    end
  end
  return maxlen
end

local function col_max_len(tbl, j)
  local maxlen = scan_rows(tbl.head.rows, j, 0)
  for _, body in ipairs(tbl.bodies) do
    maxlen = scan_rows(body.body, j, maxlen)
    maxlen = scan_rows(body.head, j, maxlen)
  end
  maxlen = scan_rows(tbl.foot.rows, j, maxlen)
  return maxlen
end

local function desired_width(j, n, len)
  -- ~0.012\linewidth per character, plus padding; first column keeps a floor.
  local w = 0.04 + 0.012 * len
  if j == 1 then
    return math.max(MIN_FIRST, math.min(MAX_FIRST, w))
  end
  return math.max(MIN_COL, math.min(0.72, w))
end

function Table(tbl)
  local n = #tbl.colspecs
  if n == 0 then
    return nil
  end
  local first_len = col_max_len(tbl, 1)
  local first = desired_width(1, n, first_len)
  local want = { first }
  local rest_sum = 0
  for j = 2, n do
    want[j] = desired_width(j, n, col_max_len(tbl, j))
    rest_sum = rest_sum + want[j]
  end
  local budget = 1 - first
  if n == 1 then
    want[1] = 1
  elseif rest_sum > 0 then
    for j = 2, n do
      want[j] = budget * (want[j] / rest_sum)
    end
  else
    local even = budget / (n - 1)
    for j = 2, n do
      want[j] = even
    end
  end
  for j = 1, n do
    tbl.colspecs[j] = { tbl.colspecs[j][1], want[j] }
  end
  return tbl
end

if not FORMAT:match("latex") then
  return {}
end

return { { Table = Table } }
