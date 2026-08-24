-- Pandoc Lua filter: strip non-ASCII from image alt/title for LaTeX.
--
-- ucharclasses CJK transitions inside \includegraphics[...,alt={…}] break
-- TeX's optional-argument scanner ("Missing } inserted"). Captions stay
-- intact via a separate Image → Figure pipeline; only the alt= key is cleared
-- when it contains characters outside ASCII.

local function has_non_ascii(s)
  if not s or s == "" then
    return false
  end
  return s:find("[\128-\255]") ~= nil
end

function Image(el)
  if not FORMAT:match("latex") then
    return nil
  end
  if has_non_ascii(el.title) then
    el.title = ""
  end
  if el.attributes and has_non_ascii(el.attributes.alt) then
    el.attributes.alt = nil
  end
  return el
end
