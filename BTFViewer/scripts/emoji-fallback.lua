-- Pandoc Lua filter: DejaVu (PDF body/mono) has no ❌ / 🟢 / 🟡 / 🔴.
-- GitHub markdown keeps the UI glyphs; LaTeX gets substitutes that exist in
-- the TeX text font (\textbullet) or DejaVu (✗).

local REPL_LATEX = {
  [0x274C] = pandoc.RawInline("latex", "{\\bfseries\\sffamily x}"), -- ❌
  [0x1F7E2] = pandoc.RawInline("latex", "{\\color{green}\\textbullet}"), -- 🟢
  [0x1F7E1] = pandoc.RawInline("latex", "{\\color{yellow}\\textbullet}"), -- 🟡
  [0x1F534] = pandoc.RawInline("latex", "{\\color{red}\\textbullet}"), -- 🔴
}

local REPL_PLAIN = {
  [0x274C] = "x",
  [0x1F7E2] = "[green]",
  [0x1F7E1] = "[yellow]",
  [0x1F534] = "[red]",
}

local function has_mapped(s)
  if type(s) ~= "string" or s == "" then
    return false
  end
  for _, cp in utf8.codes(s) do
    if REPL_LATEX[cp] then
      return true
    end
  end
  return false
end

local function replace_plain(s)
  local out = {}
  for _, cp in utf8.codes(s) do
    out[#out + 1] = REPL_PLAIN[cp] or utf8.char(cp)
  end
  return table.concat(out)
end

local function replace_inlines(text)
  local acc = {}
  local buf = {}
  local function flush()
    if #buf > 0 then
      acc[#acc + 1] = pandoc.Str(table.concat(buf))
      buf = {}
    end
  end
  for _, cp in utf8.codes(text) do
    local repl = REPL_LATEX[cp]
    if repl then
      flush()
      acc[#acc + 1] = repl
    else
      buf[#buf + 1] = utf8.char(cp)
    end
  end
  flush()
  return acc
end

function Str(el)
  if not has_mapped(el.text) then
    return nil
  end
  return replace_inlines(el.text)
end

function Code(el)
  if not has_mapped(el.text) then
    return nil
  end
  el.text = replace_plain(el.text)
  return el
end

function CodeBlock(el)
  if not has_mapped(el.text) then
    return nil
  end
  el.text = replace_plain(el.text)
  return el
end

if not FORMAT:match("latex") then
  return {}
end

return {
  { Str = Str, Code = Code, CodeBlock = CodeBlock },
}
