-- Pandoc Lua filter: same-folder Foo.md links become Foo.pdf in LaTeX.
--
-- GitHub keeps [Statistics](STATISTICS.md#timeline-anomalies). The LaTeX
-- writer emits \href{STATISTICS.md#…}, which does not open the built PDF
-- and cannot land on \hypertarget destinations. Rewrite known sibling
-- manuals to the files `make doc` writes under builds/.

local known = {
  ["README.md"] = true,
  ["STATISTICS.md"] = true,
  ["AI.md"] = true,
  ["WORKFLOWS.md"] = true,
  ["README_zh-TW.md"] = true,
  ["STATISTICS_zh-TW.md"] = true,
  ["AI_zh-TW.md"] = true,
  ["WORKFLOWS_zh-TW.md"] = true,
}

local function rewrite(target)
  local path, hash = target:match("^(.-)(#.*)$")
  if not path then
    path, hash = target, ""
  end
  path = path:gsub("^%./", "")
  if known[path] then
    return path:gsub("%.md$", ".pdf") .. hash
  end
  return nil
end

function Link(el)
  if not FORMAT:match("latex") then
    return nil
  end
  local new = rewrite(el.target)
  if not new then
    return nil
  end
  el.target = new
  return el
end
