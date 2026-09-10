import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { readFileSync } from 'node:fs'

const dlg = readFileSync(
  new URL('../src/components/InvestigationNotebookDialog.vue', import.meta.url), 'utf8')
const aiPanel = readFileSync(
  new URL('../src/components/AiAssistantPanel.vue', import.meta.url), 'utf8')
const app = readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8')
const ai = readFileSync(new URL('../src/utils/investigationAi.js', import.meta.url), 'utf8')

describe('4-step Notebook shell (replaces the six-section master/detail)', () => {
  it('has four steps navigated via transient view.step, not activeSection', () => {
    assert.match(dlg, /reactive\(\{/)
    assert.match(dlg, /view\.step/)
    for (const label of ['Question', 'Evidence', 'Verify', 'Conclusion']) {
      assert.ok(dlg.includes(`'${label}'`) || dlg.includes(`>${label}<`) || dlg.includes(label),
        `missing step label ${label}`)
    }
    // the old six-section master/detail must be gone
    assert.ok(!dlg.includes('activeSection'), 'old activeSection master/detail still present')
    assert.ok(!/class="nb-nav"/.test(dlg), 'old six-section nav class still present')
    assert.ok(!dlg.includes("NB_SECTION_ORDER"), 'old NB_SECTION_ORDER import/reference still present')
  })

  it('has Header / Step nav / Context strip / Working area / Footer regions', () => {
    assert.match(dlg, /class="nb-header"/)
    assert.match(dlg, /class="nb-step-nav"/)
    assert.match(dlg, /class="nb-context-strip"/)
    assert.match(dlg, /class="nb-working"/)
    assert.match(dlg, /class="nb-footer"/)
    assert.match(dlg, /grid-template-columns: minmax\(0, 1fr\) 360px/)
  })

  it('keeps History restore, Import/Export, Evidence package, and adds Close investigation', () => {
    assert.match(dlg, /History…/)
    assert.match(dlg, /emit\('restore'/)
    assert.match(dlg, /onImportFile/)
    assert.match(dlg, /exportJson/)
    assert.match(dlg, /emitEvidencePackage/)
    assert.match(dlg, /NB_STATUS_CLOSED/)
    assert.match(dlg, /Close investigation/)
  })

  it('header never flex-wraps — a long title must not drop More/Close to a misplaced row (layout fix)', () => {
    // A long question title used to make .nb-header wrap: header-right
    // (More/minimize/close) dropped to its own line where
    // justify-content: space-between collapsed it to the LEFT edge. .nb-menu
    // (position: absolute; right: 0 relative to that misplaced .nb-more)
    // then opened almost entirely off-screen to the left — invisible and
    // unclickable. The title already wraps within its own box
    // (.nb-header-title has white-space: normal, .nb-header-left has
    // min-width: 0 to shrink) so the header itself must stay nowrap.
    const headerRule = dlg.slice(dlg.indexOf('.nb-header {'), dlg.indexOf('.nb-header-left {'))
    assert.ok(!/flex-wrap:\s*wrap/.test(headerRule), 'nb-header must not flex-wrap')
    assert.match(dlg, /\.nb-header-title\s*\{[^}]*white-space:\s*normal/)
    assert.match(dlg, /\.nb-header-left\s*\{[^}]*min-width:\s*0/)
  })

  it('has a "New investigation" action that clears the notebook (Q1 fix)', () => {
    // There was no way to clear the current notebook and restart — only
    // "Close investigation" (marks closed, keeps content). This adds a
    // genuinely blank investigation, built with one commit() so a stray
    // click is a single Undo away.
    assert.match(dlg, /New investigation…/)
    assert.match(dlg, /function startNewInvestigation\(\)/)
    assert.match(dlg, /commit\(newInvestigation\(\{/)
    assert.match(dlg, /newInvestigation,\n/)
  })
})

describe('Question step', () => {
  it('has a question textarea, recorded scope, top findings, and Start investigation', () => {
    assert.match(dlg, /topFindingsForStart\(/)
    assert.match(dlg, /class="nb-question-input"/)
    assert.match(dlg, /view\.draftQuestion/)
    assert.ok(dlg.includes('What do you want to understand'))
    assert.ok(dlg.includes('Start investigation'))
  })

  it('commits the question + selected finding as one update() transaction', () => {
    assert.match(dlg, /function startInvestigation/)
    const fnBody = dlg.slice(dlg.indexOf('function startInvestigation'), dlg.indexOf('function useRefinedQuestion'))
    const commitCalls = fnBody.match(/commit\(/g) || []
    assert.equal(commitCalls.length, 1, 'startInvestigation must call commit() exactly once')
  })

  it('never pre-fills the question draft from a fresh investigation\'s auto-seeded title', () => {
    // ensureInvestigation() in App.vue seeds a brand-new investigation's
    // title with the tab/file name — that is not a real question, so a
    // fresh Question screen must start with an empty draft regardless of
    // whatever inv.title currently holds.
    const mounted = dlg.slice(dlg.indexOf('onMounted(() => {'), dlg.indexOf('onBeforeUnmount('))
    assert.match(mounted, /view\.draftQuestion = investigationHasContent\.value \? \(inv\.value\.title \|\| ''\) : ''/)
  })

  it('leaves edit mode after Start investigation, so returning to Question shows the read-only summary', () => {
    const fnBody = dlg.slice(dlg.indexOf('function startInvestigation'), dlg.indexOf('function useRefinedQuestion'))
    assert.match(fnBody, /questionEditing\.value = false/)
  })

  it('shows existing investigations with Edit question / Continue investigation', () => {
    assert.match(dlg, /investigationHasContent/)
    assert.ok(dlg.includes('Edit question'))
    assert.ok(dlg.includes('Continue investigation'))
  })
})

describe('Evidence step', () => {
  it('has selection state, a next-action resolver, and query-ai for per-item Ask AI', () => {
    assert.match(dlg, /selectedEvidenceIds/)
    assert.match(dlg, /function resolveEvidenceNextAction/)
    assert.match(dlg, /emit\('query-ai'/)
    assert.ok(dlg.includes('Add evidence'))
    assert.ok(dlg.includes('Ask AI about this'))
  })

  it('reuses the unchanged evidence-navigation and restore-scope plumbing', () => {
    assert.match(dlg, /onEvidenceJump/)
    assert.match(dlg, /restorePlan\(/)
    assert.match(dlg, /evidenceScopeRestorePlan/)
    assert.match(dlg, /emit\('restore-evidence-scope'/)
    assert.match(dlg, /emit\('undo-scope-restore'/)
    assert.match(dlg, /emit\('jump-range'/)
    assert.match(dlg, /emit\('open-statistics'/)
  })

  it('the two source buttons have distinct labels and close the modal so the nav is visible', () => {
    // was: two buttons both labelled "View source" that jumped the timeline /
    // opened Statistics *behind* the full-screen Notebook — nothing happened.
    const actions = dlg.slice(dlg.indexOf('class="nb-ev-actions"'), dlg.indexOf('class="nb-ev-details"'))
    assert.match(actions, /View source/)
    assert.match(actions, /Open Statistics/)
    assert.ok(!/View source[\s\S]{0,300}View source/.test(actions), 'duplicate "View source" label still present')
    assert.match(actions, /@click="emit\('close'\); onEvidenceJump\(it\.nav\)"/)
    assert.match(actions, /@click="emit\('close'\); emit\('open-statistics', it\.nav\.stats_metric\)"/)
  })

  it('each evidence card has a direct delete icon (no more "…" menu)', () => {
    const actions = dlg.slice(dlg.indexOf('class="nb-ev-actions"'), dlg.indexOf('class="nb-ev-details"'))
    assert.match(actions, /class="nb-ev-action muted nb-ev-delete"/)
    assert.match(actions, /aria-label="Delete evidence"/)
    assert.match(actions, /@click="removeEvidenceWithConfirm\(it\.bookmark_id\)"/)
    assert.match(dlg, /function removeEvidenceWithConfirm\(id\) \{/)
    assert.match(dlg, /commit\(removeBookmark\(props\.investigation, id\)\)/)
    // the single-item "…" popup menu is gone
    assert.ok(!dlg.includes('evidenceMoreFor'), 'evidenceMoreFor state still present')
    assert.ok(!dlg.includes('nb-ev-more-wrap'), 'old nb-ev-more-wrap still present')
  })

  it('implements the §5 next-action table in priority order', () => {
    const body = dlg.slice(
      dlg.indexOf('function resolveEvidenceNextAction'),
      dlg.indexOf('const evidenceNextAction'))
    const order = ['aiRequestState.busy', 'hasPendingProposal', 'evidenceCount === 0', 'selectedCount > 0', 'selectedCount === 0']
    let lastIndex = -1
    for (const token of order) {
      const idx = body.indexOf(token)
      assert.ok(idx > lastIndex, `resolver checks out of order at ${token}`)
      lastIndex = idx
    }
  })

  it('the zero-selected next action actually ticks every evidence item (was a dead no-op)', () => {
    const body = dlg.slice(dlg.indexOf('function onEvidenceNextAction'),
      dlg.indexOf('const verifyNextAction'))
    const sel = body.slice(body.indexOf("a.id === 'select'"))
    assert.match(sel, /view\.selectedEvidenceIds = sections\.value\.evidence\.items\.map/)
    assert.match(dlg, /label: 'Select all evidence'/)
  })

  it('"Ask AI about this" closes the modal so the AI panel reply is visible', () => {
    assert.match(dlg, /@click="emit\('close'\); emit\('query-ai', \{ prompt: buildAskAboutEvidencePrompt\(it\) \}\)"/)
  })
})

describe('Verify step', () => {
  it('has explanation cards with support/contradict groups and a Link evidence picker', () => {
    assert.ok(dlg.includes('Test possible explanations'))
    assert.ok(dlg.includes('Supporting evidence'))
    assert.ok(dlg.includes('Contradicting evidence'))
    assert.ok(dlg.includes('Checks to complete'))
    assert.ok(dlg.includes('Link evidence'))
    assert.ok(dlg.includes('Suggest explanations'))
    assert.match(dlg, /linkBookmarks\(/)
    assert.match(dlg, /function explanationLinks/)
  })

  it('drops the old generic From/Relation/To link form', () => {
    assert.ok(!dlg.includes('nb-link-sel'), 'old From/Relation/To select markup still present')
  })
})

describe('Conclusion step', () => {
  it('has an editable conclusion, cited evidence, unresolved checks, stale refs, limitations, export', () => {
    assert.ok(dlg.includes('Summarize what the evidence supports'))
    assert.match(dlg, /class="nb-conclusion-box"/)
    assert.match(dlg, /setConclusion\(/)
    assert.match(dlg, /conclusionEvidenceChains\(/)
    assert.match(dlg, /detectBrokenReferences/)
    assert.ok(dlg.includes('Cited evidence'))
    assert.ok(dlg.includes('Unresolved checks'))
    assert.ok(dlg.includes('Stale references'))
    assert.ok(dlg.includes('Limitations'))
    assert.ok(dlg.includes('Export report'))
    assert.ok(dlg.includes('Preview report'))
  })
})

describe('AI assistance bridging (single shared request, no new concurrency system)', () => {
  it('accepts aiRequestState / hasPendingProposal / refineSuggestion as props', () => {
    assert.match(dlg, /aiRequestState:\s*\{/)
    assert.match(dlg, /hasPendingProposal:\s*\{/)
    assert.match(dlg, /refineSuggestion:\s*\{/)
  })

  it('routes every AI action through the collaborate() helper (tags sourceStep)', () => {
    for (const action of ['refine_question', 'draft_hypotheses', 'draft_conclusion', 'review_investigation']) {
      assert.ok(dlg.includes(`collaborate('${action}'`), `missing collaborate action ${action}`)
    }
  })

  it('adds refine_question additively to NB_AI_ACTIONS, keeping the original six', () => {
    assert.match(ai, /refine_question/)
    assert.match(ai, /parseQuestionSuggestion/)
    for (const id of ['review_investigation', 'suggest_next_check', 'draft_hypotheses',
      'draft_conclusion', 'update_from_findings', 'compare_trace']) {
      assert.ok(ai.includes(`'${id}'`), `lost existing action ${id}`)
    }
  })
})

describe('Responsive layout', () => {
  it('collapses the working area to one column under 1000px via CSS', () => {
    assert.match(dlg, /@media \(max-width: 1000px\)/)
  })

  it('switches to a JS-driven compact step selector under 720px', () => {
    assert.match(dlg, /matchMedia\('\(max-width: 720px\)'\)/)
    assert.match(dlg, /isCompactStepNav/)
    assert.match(dlg, /stepSelectorOpen/)
  })
})

describe('Keyboard behavior', () => {
  it('Escape closes the innermost open menu before closing the dialog', () => {
    assert.match(dlg, /@keydown\.esc="onEscape"/)
    assert.match(dlg, /function onEscape/)
  })
})

describe('Moveable window', () => {
  it('drags from the header (excluding its own buttons/inputs) to a fixed position', () => {
    assert.match(dlg, /@mousedown="onHeaderMouseDown"/)
    assert.match(dlg, /function onHeaderMouseDown/)
    assert.match(dlg, /closest\('button, input, select, textarea, a'\)/)
    assert.match(dlg, /function onHeaderMouseMove/)
    assert.match(dlg, /function onHeaderMouseUp/)
  })

  it('starts centered (no inline position) and only switches to fixed once dragged', () => {
    assert.match(dlg, /const shellPos = ref\(null\)/)
    assert.match(dlg, /shellPos \? \{ position: 'fixed'/)
  })

  it('clamps so the window can never be dragged fully off-screen', () => {
    const body = dlg.slice(dlg.indexOf('function onHeaderMouseMove'), dlg.indexOf('function onHeaderMouseUp'))
    assert.match(body, /minVisible/)
    assert.match(body, /Math\.min\(Math\.max\(/)
  })

  it('cleans up window listeners on unmount (e.g. dialog closed mid-drag)', () => {
    const body = dlg.slice(dlg.indexOf('onBeforeUnmount(() => {'), dlg.lastIndexOf('})'))
    assert.match(body, /removeEventListener\('mousemove', onHeaderMouseMove\)/)
    assert.match(body, /removeEventListener\('mouseup', onHeaderMouseUp\)/)
  })

  it('swallows the trailing click after a real drag, so releasing over the backdrop cannot close the dialog', () => {
    // Browsers fire a `click` at the mouseup point after any drag; if that
    // point lands on .dialog-overlay (not the shell we just moved there),
    // the overlay's @click.self would close the window out from under the
    // user. A no-op mousedown+mouseup (no movement) must NOT suppress the
    // next click — only a genuine drag should.
    assert.match(dlg, /dragState\.moved = true/)
    assert.match(dlg, /function suppressTrailingClick/)
    const upBody = dlg.slice(dlg.indexOf('function onHeaderMouseUp'), dlg.indexOf('onMounted('))
    assert.match(upBody, /if \(moved\)/)
    assert.match(upBody, /addEventListener\('click', suppressTrailingClick, \{ capture: true, once: true \}\)/)
  })
})

describe('Undo/redo and footer', () => {
  it('keeps undo/redo wired and adds step Prev/Next', () => {
    assert.match(dlg, /emit\('undo'\)/)
    assert.match(dlg, /emit\('redo'\)/)
    assert.match(dlg, /goPrevStep/)
    assert.match(dlg, /goNextStep/)
  })
})

describe('App.vue wiring stays intact for the redesigned dialog', () => {
  it('keeps every existing emit handler bound', () => {
    for (const h of ['notebookApply', 'notebookUndoAction', 'notebookRedoAction',
      'notebookRestoreAction', 'onScaffoldNotebook', 'onNotebookJumpRange',
      'onExportAiEvidencePackage', 'onNotebookCollaborate', 'onRestoreEvidenceScope',
      'onUndoScopeRestore']) {
      assert.ok(app.includes(h), `App.vue missing handler ${h}`)
    }
  })

  it('adds query-ai / focus-ai-panel / cancel-ai-request wiring and the new bridging props', () => {
    assert.match(app, /@query-ai="queryAnalysisWithAi"/)
    assert.match(app, /ai-request-state/)
    assert.match(app, /has-pending-proposal/)
    assert.match(app, /@focus-ai-panel=/)
    assert.match(app, /@cancel-ai-request=/)
    assert.match(app, /aiPanelRequestState/)
  })

  it('Cancel request actually cancels the in-flight AI call, not just switches tabs', () => {
    // The Notebook is a full-screen modal over the AI panel — merely
    // switching rightPanelTab underneath it would be unreachable/invisible
    // to the user, so Cancel must call AiAssistantPanel's real stop().
    assert.match(dlg, /emit\('cancel-ai-request'\)/)
    assert.match(app, /aiPanelRef\?\.cancelRequest\?\.\(\)/)
    assert.match(aiPanel, /cancelRequest:\s*\(\)\s*=>\s*stop\(\)/)
  })

  it('threads selectedEvidenceIds through onNotebookCollaborate into collaborateContext', () => {
    assert.match(app, /onNotebookCollaborate\(\{ action = '', selectedEvidenceIds = null, sourceStep = '' \}/)
    assert.match(app, /collaborateContext\(investigation\.value, \{ action, findings, selectedEvidenceIds \}\)/)
  })

  it('collaborate() helper tags every request with the source step; App.vue threads it back as lastAiReply', () => {
    // Fix for "I don't see any changes... do I need to close the notebook":
    // every emit('collaborate', ...) site routes through one helper that
    // stamps sourceStep, so the reply can be shown back on that same step.
    assert.match(dlg, /function collaborate\(action, extra = \{\}\) \{/)
    assert.match(dlg, /emit\('collaborate', \{ action, sourceStep: view\.step, \.\.\.extra \}\)/)
    assert.ok(!/emit\('collaborate', \{ action:/.test(dlg))
    assert.match(dlg, /stepAiReplyText/)
    assert.match(dlg, /lastAiReply: \{ type: Object, default: null \}/)
    assert.match(app, /notebookCollab\.value\.lastReplyText = replyText/)
    assert.match(app, /:last-ai-reply="notebookCollab \? \{ step: notebookCollab\.sourceStep, text: notebookCollab\.lastReplyText \} : null"/)
  })
})

describe('§9 AI panel notebook-collab banner (unchanged)', () => {
  it('AI panel still shows a compact notebook context banner with a folded digest', () => {
    assert.match(aiPanel, /ai-notebook-collab/)
    assert.match(aiPanel, /notebookCollab/)
    assert.match(aiPanel, /clear-notebook-collab/)
    assert.match(aiPanel, /notebook-proposal/)
    assert.match(aiPanel, /What the AI receives/)
    assert.match(aiPanel, /collabDigestHtml/)
  })

  it('exposes read-only requestStatus/lastAssistantText for the Notebook bridge', () => {
    assert.match(aiPanel, /requestStatus:\s*\(\)\s*=>/)
    assert.match(aiPanel, /lastAssistantText:\s*\(\)\s*=>/)
  })

  it('collaboration still sends a readable digest, never raw JSON in the chat', () => {
    assert.match(app, /collaborateDigest\(/)
    assert.match(app, /askNotebook\(/)
    assert.ok(!/JSON\.stringify\(\s*ctx\.investigation/.test(app))
    assert.ok(!app.includes('```json'))
  })
})

describe('§10 proposal review — inline in the right panel, no separate modal', () => {
  it('the inline card groups the diff and offers select / add-all / dismiss', () => {
    assert.match(dlg, /validateProposal\(/)
    assert.match(dlg, /proposalDiff\(/)
    for (const t of ['Add selected (', 'Add all', 'Dismiss', 'needs_confirmation']) {
      assert.ok(dlg.includes(t), `inline proposal card missing ${t}`)
    }
    // the standalone modal component is gone
    assert.ok(!app.includes('NotebookProposalDialog'), 'NotebookProposalDialog still referenced in App.vue')
  })

  it('App applies an accepted proposal as one undo step, nothing automatic', () => {
    assert.match(app, /onNotebookProposal\b/)
    assert.match(app, /onNotebookProposalApply/)
    assert.match(app, /applyProposal\(/)
    assert.match(app, /pushNotebookState\(/)
  })
})

describe('§10 proposal review is shown inline in the Notebook right panel', () => {
  it('the dialog validates + diffs the proposal itself and renders a select-and-add card', () => {
    assert.match(dlg, /aiProposal:\s*\{/)
    assert.match(dlg, /\bvalidateProposal\b/)
    assert.match(dlg, /\bproposalDiff\b/)
    assert.match(dlg, /nb-proposal-card/)
    assert.match(dlg, /nb-prop-op/)
    for (const t of ['AI proposal', 'Add selected (', 'Add all', 'Not applicable (']) {
      assert.ok(dlg.includes(t), `inline proposal card missing ${t}`)
    }
  })

  it('per-op checkbox + needs_confirmation sub-checkbox, then emits apply-proposal', () => {
    assert.match(dlg, /toggleProposalOp\(/)
    assert.match(dlg, /toggleProposalConfirm\(/)
    assert.match(dlg, /op\.status === 'needs_confirmation'/)
    assert.match(dlg, /emit\('apply-proposal', \{/)
    assert.match(dlg, /emit\('dismiss-proposal'\)/)
  })

  it('App threads notebookProposal into the dialog and wires apply/dismiss back', () => {
    assert.match(app, /:ai-proposal="notebookProposal"/)
    assert.match(app, /@apply-proposal="onNotebookProposalApply"/)
    // dismiss clears both the proposal and the collab context (stale reply too)
    assert.match(app, /@dismiss-proposal="notebookProposal = null; notebookCollab = null"/)
    // no separate modal — onNotebookProposal just opens the Notebook to review inline
    assert.ok(!app.includes('NotebookProposalDialog'))
    const fn = app.slice(app.indexOf('function onNotebookProposal('), app.indexOf('function onNotebookProposalApply'))
    assert.match(fn, /notebookProposal\.value = proposal/)
    assert.match(fn, /notebookDialogOpen\.value = true/)
  })

  it('replacing / restoring / closing the investigation drops a pending AI proposal', () => {
    for (const fn of ['function startNewInvestigation', 'function closeInvestigation',
      'function restoreSnapshot', 'async function onImportFile']) {
      const body = dlg.slice(dlg.indexOf(fn), dlg.indexOf(fn) + 600)
      assert.match(body, /emit\('dismiss-proposal'\)/, `${fn} must drop the pending proposal`)
    }
  })

  it('a prose reply renders as demo-style titled sections + bullets, not a raw pre-wrap dump', () => {
    assert.match(dlg, /stepAiReplyBlocks\b/)
    assert.match(dlg, /nb-assist-note-list/)
    assert.match(dlg, /v-for="\(blk, bi\) in stepAiReplyBlocks"/)
    // the old raw text block is gone
    assert.ok(!dlg.includes('class="nb-assist-reply"'))
    assert.ok(!/white-space:\s*pre-wrap/.test(dlg.slice(dlg.indexOf('.nb-assist-note'))))
  })

  it('a review-only proposal (summary + notes, no ops) renders a lean card — no dead links', () => {
    assert.match(dlg, /proposalReview\.summary/)
    assert.match(dlg, /proposalReview\.notes/)
    assert.match(dlg, /nb-proposal-summary/)
    assert.match(dlg, /nb-proposal-notes/)
    // no non-functional links / filler on the proposal card
    assert.ok(!dlg.includes('Open in AI Assistant'))
    assert.ok(!dlg.includes('Review only — no changes to add'))
    // add buttons are gated on .ok; Dismiss is always there
    const actions = dlg.slice(dlg.indexOf('class="nb-prop-actions"'))
    assert.match(actions, /Dismiss/)
    assert.match(actions.slice(0, actions.indexOf('</div>') + 6), /v-if="proposalReview\.ok"/)
  })

  it('AiAssistantPanel parses the proposal via the shared tolerant extractor, on every turn', () => {
    assert.match(aiPanel, /import \{ extractNotebookProposal(?:, [^}]+)? \} from '\.\.\/utils\/investigationAi\.js'/)
    assert.match(aiPanel, /const obj = extractNotebookProposal\(text\)/)
    // §10: also scanned from ingestTurn, so an agentic gather_evidence loop
    // that emits the proposal in a tool-call turn is not missed
    const ingest = aiPanel.slice(aiPanel.indexOf('function ingestTurn'), aiPanel.indexOf('function findBatch'))
    assert.match(ingest, /if \(text\) maybeEmitNotebookProposal\(text\)/)
    // the messy-reply handling lives in the util, not re-implemented here
    assert.match(ai, /export function extractNotebookProposal/)
    assert.match(ai, /stripListMarkers/)
  })

  it('a leaked structured proposal is never shown as prose in the Notebook', () => {
    const body = dlg.slice(dlg.indexOf('const stepAiReplyBlocks = computed'),
      dlg.indexOf('const stepAiReplyBlocks = computed') + 500)
    assert.match(body, /replace\(\/```\(\?:json\)\?/)
    assert.match(body, /btfnext\|btfstats/)
  })

  it('the AI panel chat log also summarises a proposal reply (aiMarkdown, both platforms)', () => {
    const md = readFileSync(new URL('../src/utils/aiMarkdown.js', import.meta.url), 'utf8')
    assert.match(md, /import \{ summarizeNotebookProposalForChat \} from '\.\/investigationAi\.js'/)
    assert.match(md, /body = summarizeNotebookProposalForChat\(body\)/)
    assert.match(ai, /export function summarizeNotebookProposalForChat/)
  })

  it('the collaborate prompts declare the proposal schema (structured, parseable replies)', () => {
    assert.match(ai, /NB_PROPOSAL_REPLY_FORMAT/)
    assert.match(ai, /btf-viewer-nb-proposal\/1/)
    assert.match(ai, /NB_AI_TASKS/)
  })
})
