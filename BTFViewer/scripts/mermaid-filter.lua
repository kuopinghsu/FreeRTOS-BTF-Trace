-- Pandoc Lua filter: render ```mermaid code blocks to PNG figures for PDF/DOCX.
-- Requires Node.js and @mermaid-js/mermaid-cli (invoked via `mmdc` or `npx`).
--
-- Cache: builds/mermaid-cache/<sha1>.png (relative to the filter's CWD, usually
-- BTFViewer/ when running `make doc`).
--
-- Optional env:
--   MERMAID_BIN   absolute path to mmdc (default: mmdc on PATH, else npx)
--   MERMAID_CACHE directory for cached PNGs (default: builds/mermaid-cache)

local system = require("pandoc.system")
local path = require("pandoc.path")
local sha1 = pandoc.utils.sha1

local function cache_dir()
  local env = os.getenv("MERMAID_CACHE")
  if env and env ~= "" then
    return env
  end
  return "builds/mermaid-cache"
end

local function ensure_dir(dir)
  system.make_directory(dir, true)
end

local function file_exists(fname)
  local f = io.open(fname, "rb")
  if f then
    f:close()
    return true
  end
  return false
end

local function which(cmd)
  local pipe = io.popen("command -v " .. cmd .. " 2>/dev/null")
  if not pipe then
    return nil
  end
  local out = pipe:read("*l")
  pipe:close()
  if out and out ~= "" then
    return out
  end
  return nil
end

local function write_file(fname, text)
  local f = assert(io.open(fname, "wb"))
  f:write(text)
  f:close()
end

local function run_mmdc(mmd_path, png_path, puppeteer_cfg)
  local bin = os.getenv("MERMAID_BIN")
  local prog
  local args
  if bin and bin ~= "" then
    prog = bin
    args = { "-i", mmd_path, "-o", png_path, "-b", "white", "-p", puppeteer_cfg }
  elseif which("mmdc") then
    prog = "mmdc"
    args = { "-i", mmd_path, "-o", png_path, "-b", "white", "-p", puppeteer_cfg }
  elseif which("npx") then
    prog = "npx"
    args = {
      "--yes", "@mermaid-js/mermaid-cli@11.4.2",
      "-i", mmd_path, "-o", png_path, "-b", "white", "-p", puppeteer_cfg,
    }
  else
    error(
      "mermaid filter: need mmdc or npx (Node.js). "
        .. "Install: npm i -g @mermaid-js/mermaid-cli"
    )
  end
  local ok, err = pcall(function()
    pandoc.pipe(prog, args, "")
  end)
  if not ok then
    io.stderr:write("[mermaid] mmdc error: " .. tostring(err) .. "\n")
    return false
  end
  return true
end

function CodeBlock(el)
  if not el.classes:includes("mermaid") then
    return nil
  end
  local dir = cache_dir()
  ensure_dir(dir)
  local hash = sha1(el.text)
  local png = path.join({ dir, hash .. ".png" })
  local mmd = path.join({ dir, hash .. ".mmd" })
  local puppeteer_cfg = path.join({ dir, "puppeteer.json" })

  if not file_exists(puppeteer_cfg) then
    write_file(
      puppeteer_cfg,
      '{"args":["--no-sandbox","--disable-setuid-sandbox","--disable-gpu"]}\n'
    )
  end

  if not file_exists(png) then
    write_file(mmd, el.text .. "\n")
    io.stderr:write("[mermaid] rendering " .. hash:sub(1, 8) .. "…\n")
    if not run_mmdc(mmd, png, puppeteer_cfg) or not file_exists(png) then
      error(
        "mermaid filter: failed to render diagram "
          .. hash:sub(1, 8)
          .. " (need Node.js; first run downloads Chromium via npx)"
      )
    end
  end

  local alt = "Mermaid diagram"
  if el.attributes.title and el.attributes.title ~= "" then
    alt = el.attributes.title
  elseif el.attributes.caption and el.attributes.caption ~= "" then
    alt = el.attributes.caption
  end
  local img = pandoc.Image({ pandoc.Str(alt) }, png)
  img.attributes["width"] = el.attributes.width or "90%"
  return pandoc.Para({ img })
end
