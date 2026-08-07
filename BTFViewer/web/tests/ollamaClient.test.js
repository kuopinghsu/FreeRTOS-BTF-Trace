import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  buildAiSystemPrompt,
  isLocalOllamaUrl,
  normalizeOllamaUrl,
  ollamaSameOriginProxyBase,
} from '../src/utils/ollamaClient.js'

describe('ollama URL helpers', () => {
  it('normalizes trailing slash and /api', () => {
    assert.equal(normalizeOllamaUrl('http://localhost:11434/'), 'http://localhost:11434')
    assert.equal(normalizeOllamaUrl('http://localhost:11434/api'), 'http://localhost:11434')
  })

  it('detects local Ollama hosts', () => {
    assert.equal(isLocalOllamaUrl('http://localhost:11434'), true)
    assert.equal(isLocalOllamaUrl('http://127.0.0.1:11434'), true)
    assert.equal(isLocalOllamaUrl('https://ollama.com'), false)
  })

  it('same-origin proxy is null without a browser window', () => {
    assert.equal(ollamaSameOriginProxyBase('http://localhost:11434'), null)
  })

  it('buildAiSystemPrompt includes reply language', () => {
    assert.match(buildAiSystemPrompt('English'), /Always write your entire reply in English/)
    assert.match(
      buildAiSystemPrompt('Japanese (日本語)'),
      /Always write your entire reply in Japanese \(日本語\)/,
    )
  })
})
