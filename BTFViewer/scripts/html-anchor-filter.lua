-- Pandoc Lua filter: turn GitHub HTML anchors into PDF hypertargets.
--
-- README/STATISTICS use `<a id="foo" name="foo">` so GitHub links stay stable
-- when the heading text changes. Pandoc's LaTeX writer otherwise drops those
-- raw HTML tags, so `\hyperref[foo]` has no target and makePDF warns
-- "Hyper reference `foo' undefined".
--
-- Pandoc already emits `\label{id}` / `\hypertarget{id}` for a heading whose
-- auto-id matches the HTML id. Re-emitting `\label` then duplicates it.
-- GitHub slugs that differ from the heading auto-id (Keyboard & mouse →
-- `keyboard--mouse` vs `keyboard-mouse`) still need an explicit label.
--
-- `<a id="foo">&#x200B;</a>` immediately followed by `---` is a Setext
-- heading whose title is a zero-width space. Injecting LaTeX into that
-- title breaks KOMA `\section`. Those artifacts become a plain anchor.

local function extract_id(html)
  if type(html) ~= "string" then
    return nil
  end
  local id = html:match('[iI][dD]%s*=%s*"([^"]+)"')
    or html:match("[iI][dD]%s*=%s*'([^']+)'")
    or html:match('[nN][aA][mM][eE]%s*=%s*"([^"]+)"')
    or html:match("[nN][aA][mM][eE]%s*=%s*'([^']+)'")
  if id and id ~= "" then
    return id
  end
  return nil
end

local ZWSP = "\226\128\139"

local header_ids = {}

local function collect_header(el)
  if el.identifier and el.identifier ~= "" then
    header_ids[el.identifier] = true
  end
end

local function latex_anchor(id)
  -- Pandoc emits \hyperref[id] for [text](#id). That needs \label{id}, not
  -- only \hypertarget (a PDF dest for \hyperlink / cross-file href#id).
  -- \phantomsection so the label is not tied to the previous numbered heading.
  return pandoc.RawInline(
    "latex",
    "\\phantomsection\\label{" .. id .. "}\\hypertarget{" .. id .. "}{}"
  )
end

local function is_zwsp(inline)
  return inline.t == "Str" and inline.text == ZWSP
end

local function header_html_ids(el)
  local ids = {}
  local kept = {}
  for _, inline in ipairs(el.content) do
    if inline.t == "RawInline" and inline.format == "html" then
      local id = extract_id(inline.text)
      if id then
        ids[#ids + 1] = id
      end
    elseif not is_zwsp(inline) then
      kept[#kept + 1] = inline
    end
  end
  return ids, kept
end

-- Turn `<a id>` + `---` Setext headings into a standalone PDF anchor.
local function fix_setext_header(el)
  local ids, kept = header_html_ids(el)
  if #ids == 0 then
    return nil
  end
  if #kept == 0 then
    local blocks = {}
    for _, id in ipairs(ids) do
      if not header_ids[id] then
        blocks[#blocks + 1] = pandoc.Plain({ latex_anchor(id) })
      end
    end
    return blocks
  end
  if el.identifier == "" or el.identifier == "section" then
    el.identifier = ids[1]
  end
  el.content = kept
  return el
end

local function convert_html(el)
  if el.format ~= "html" then
    return nil
  end
  local id = extract_id(el.text)
  if not id then
    return nil
  end
  if header_ids[id] then
    return {}
  end
  return latex_anchor(id)
end

local function convert_html_block(el)
  if el.format ~= "html" then
    return nil
  end
  local id = extract_id(el.text)
  if not id then
    return nil
  end
  if header_ids[id] then
    return {}
  end
  return pandoc.Plain({ latex_anchor(id) })
end

if not FORMAT:match("latex") then
  return {}
end

return {
  { Header = collect_header },
  { Header = fix_setext_header },
  { RawInline = convert_html, RawBlock = convert_html_block },
}
