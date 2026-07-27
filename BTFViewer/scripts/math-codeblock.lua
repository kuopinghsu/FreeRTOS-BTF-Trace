-- Pandoc Lua filter: convert ```math code blocks to LaTeX display math.
-- GitHub renders ```math as display math; pandoc treats it as a code block.
-- This filter bridges the two so the same Markdown renders correctly in both.
function CodeBlock(el)
  if el.classes[1] == "math" then
    return pandoc.Math("DisplayMath", el.text)
  end
end
