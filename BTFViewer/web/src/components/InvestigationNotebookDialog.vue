<template>
  <div
    class="dialog-overlay"
    @click.self="emit('close')"
  >
    <div
      ref="shellRef"
      class="nb-shell"
      role="dialog"
      aria-modal="true"
      aria-label="Investigation notebook"
      :class="{ dragging }"
      :style="shellPos ? { position: 'fixed', left: shellPos.left + 'px', top: shellPos.top + 'px', margin: 0 } : null"
      @keydown.esc="onEscape"
    >
      <!-- Header: label/title/status · More menu · Close — mousedown here (not
           on a button/input/link inside it) drags the window. -->
      <div
        class="nb-header"
        @mousedown="onHeaderMouseDown"
      >
        <div class="nb-header-left">
          <span class="nb-header-label">Investigation Notebook</span>
          <div class="nb-header-title-row">
            <span class="nb-header-title">{{ inv.title || 'Untitled investigation' }}</span>
            <span class="nb-status-pill">
              <span
                class="nb-status-dot"
                :class="`s-${header.status}`"
              />{{ header.status_label }}
            </span>
          </div>
        </div>
        <div class="nb-header-right">
          <div class="nb-more">
            <button
              type="button"
              class="nb-icon-btn"
              title="More"
              @click="moreMenuOpen = !moreMenuOpen"
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="currentColor"
              ><circle
                cx="5"
                cy="12"
                r="1.7"
              /><circle
                cx="12"
                cy="12"
                r="1.7"
              /><circle
                cx="19"
                cy="12"
                r="1.7"
              /></svg>
            </button>
            <div
              v-if="moreMenuOpen"
              class="nb-menu"
            >
              <button
                type="button"
                class="nb-menu-item"
                :disabled="!findingOptions.length"
                :title="findingOptions.length ? 'Seed observations from the current Analysis findings' : 'No Analysis findings to seed from'"
                @click="moreMenuOpen = false; emit('scaffold')"
              >
                Add from Findings
              </button>
              <button
                type="button"
                class="nb-menu-item"
                :disabled="historyState.count < 2"
                @click="moreMenuOpen = false; historyOpen = !historyOpen"
              >
                History…
              </button>
              <button
                type="button"
                class="nb-menu-item"
                @click="moreMenuOpen = false; fileInput?.click()"
              >
                Import investigation…
              </button>
              <button
                type="button"
                class="nb-menu-item"
                @click="moreMenuOpen = false; exportJson()"
              >
                Export JSON
              </button>
              <button
                type="button"
                class="nb-menu-item"
                @click="moreMenuOpen = false; emitEvidencePackage()"
              >
                Evidence package…
              </button>
              <button
                type="button"
                class="nb-menu-item"
                @click="moreMenuOpen = false; startNewInvestigation()"
              >
                New investigation…
              </button>
              <button
                type="button"
                class="nb-menu-item danger"
                @click="moreMenuOpen = false; closeInvestigation()"
              >
                Close investigation
              </button>
            </div>
          </div>
          <button
            class="nb-icon-btn"
            type="button"
            title="Close"
            @click="emit('close')"
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linecap="round"
            ><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        </div>
        <input
          ref="fileInput"
          type="file"
          accept=".json,application/json"
          hidden
          @change="onImportFile"
        >
        <div
          v-if="historyOpen"
          class="nb-history"
        >
          <span class="nb-history-label">Restore snapshot</span>
          <button
            v-for="n in historyState.count"
            :key="n"
            type="button"
            class="nb-history-dot"
            :class="{ current: n - 1 === historyState.index }"
            :title="`Snapshot ${n} of ${historyState.count}`"
            @click="restoreSnapshot(n - 1)"
          >
            {{ n }}
          </button>
        </div>
      </div>

      <!-- Step navigation -->
      <div
        v-if="!isCompactStepNav"
        class="nb-step-nav"
      >
        <button
          v-for="s in STEP_ORDER"
          :key="s"
          type="button"
          class="nb-step-tab"
          :class="{ active: view.step === s }"
          :aria-current="view.step === s ? 'true' : undefined"
          @click="goToStep(s)"
        >
          <span class="nb-step-num">
            <svg
              v-if="stepDone[s] && view.step !== s"
              width="10"
              height="10"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="3"
              stroke-linecap="round"
              stroke-linejoin="round"
            ><path d="M5 13l4 4L19 7" /></svg>
            <template v-else>{{ STEP_ORDER.indexOf(s) + 1 }}</template>
          </span>
          {{ STEP_LABELS[s] }}
        </button>
      </div>
      <div
        v-else
        class="nb-step-nav-compact"
      >
        <button
          type="button"
          class="nb-step-compact-btn"
          aria-haspopup="listbox"
          :aria-expanded="stepSelectorOpen ? 'true' : 'false'"
          @click="stepSelectorOpen = !stepSelectorOpen"
        >
          Step {{ stepIndex + 1 }} of {{ STEP_ORDER.length }} · {{ STEP_LABELS[view.step] }}
          <svg
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          ><path d="M6 9l6 6 6-6" /></svg>
        </button>
        <ul
          v-if="stepSelectorOpen"
          role="listbox"
          class="nb-step-compact-list"
        >
          <li
            v-for="s in STEP_ORDER"
            :key="s"
          >
            <button
              type="button"
              role="option"
              :aria-selected="view.step === s ? 'true' : 'false'"
              @click="goToStep(s)"
            >
              {{ STEP_ORDER.indexOf(s) + 1 }} · {{ STEP_LABELS[s] }}
            </button>
          </li>
        </ul>
      </div>

      <!-- Context strip -->
      <div class="nb-context-strip">
        <span
          v-if="header.trace"
          class="nb-chip"
        >{{ header.trace }}</span>
        <span class="nb-chip">Scope: {{ header.scope }}</span>
        <span class="nb-chip">Filters: None</span>
        <span
          v-if="brokenCount"
          class="nb-chip warn"
        >{{ brokenCount }} stale ref{{ brokenCount === 1 ? '' : 's' }}</span>
        <span class="nb-context-spacer" />
        <button
          type="button"
          class="nb-link-btn"
          @click="contextDetailsOpen = !contextDetailsOpen"
        >
          Context details
        </button>
      </div>
      <div
        v-if="contextDetailsOpen"
        class="nb-context-details"
      >
        <p class="nb-context-details-note">
          What is actually sent to the AI when you collaborate from this
          investigation — no chat history, no other trace.
        </p>
        <pre class="nb-digest">{{ contextDigest }}</pre>
      </div>

      <!-- Working area -->
      <div class="nb-working">
        <div class="nb-main-col">
          <!-- ============ QUESTION ============ -->
          <template v-if="view.step === 'question'">
            <h2
              ref="stepHeadingRef"
              class="nb-section-title"
              tabindex="-1"
            >
              What do you want to understand?
            </h2>
            <p class="nb-section-helper">
              Start with a question about this trace.
            </p>

            <template v-if="investigationHasContent && !questionEditing">
              <div class="nb-card nb-question-display">
                <p class="nb-question-text">
                  {{ inv.title || 'Untitled investigation' }}
                </p>
                <div class="nb-card-actions">
                  <button
                    type="button"
                    class="nb-btn"
                    @click="startEditQuestion"
                  >
                    Edit question
                  </button>
                  <button
                    type="button"
                    class="nb-btn primary"
                    @click="goToStep('evidence')"
                  >
                    Continue investigation
                  </button>
                </div>
              </div>
            </template>
            <template v-else>
              <textarea
                v-model="view.draftQuestion"
                class="nb-question-input"
                rows="3"
                placeholder="What do you want to understand about this trace?"
              />

              <div class="nb-card">
                <p class="nb-card-title">
                  Recorded scope
                </p>
                <div class="nb-scope-row">
                  <div
                    v-if="header.trace"
                    class="nb-scope-item"
                  >
                    <span class="k">Trace</span><span class="v mono">{{ header.trace }}</span>
                  </div>
                  <div class="nb-scope-item">
                    <span class="k">Range</span><span class="v mono">{{ header.scope }}</span>
                  </div>
                  <div class="nb-scope-item">
                    <span class="k">Filters</span><span class="v">None active</span>
                  </div>
                  <div
                    v-if="brokenCount"
                    class="nb-scope-item"
                  >
                    <span class="k">Data quality</span>
                    <span
                      class="v"
                      style="color: var(--semantic-warning, #e67e22)"
                    >{{ brokenCount }} limitation{{ brokenCount === 1 ? '' : 's' }} — see Context details</span>
                  </div>
                </div>
              </div>

              <div
                v-if="startFindings.length"
                class="nb-card"
              >
                <p class="nb-card-title">
                  Start from a finding
                </p>
                <label
                  v-for="f in startFindings"
                  :key="f.rule_id || f.id"
                  class="nb-finding-row"
                >
                  <input
                    v-model="selectedFindingId"
                    type="radio"
                    :value="f.rule_id || f.ruleId || f.id"
                    name="nb-start-finding"
                  >
                  <span class="nb-finding-body">
                    <span class="nb-finding-title">{{ f.title || f.observation || f.rule_id }}</span>
                    <span class="nb-finding-meta">{{ f.severity || 'info' }}<template v-if="f.task"> · {{ f.task }}</template></span>
                  </span>
                </label>
              </div>

              <div
                v-if="!investigationHasContent"
                class="nb-next-card"
              >
                <div>
                  <div class="nb-next-title">
                    Start investigation
                  </div>
                  <div
                    v-if="!view.draftQuestion.trim()"
                    class="nb-next-reason"
                  >
                    Enter a question to get started.
                  </div>
                  <div
                    v-else
                    class="nb-next-reason"
                  >
                    Records this question{{ selectedFindingId ? ' and adds the selected finding as your first evidence' : '' }} in one undoable step.
                  </div>
                </div>
                <button
                  type="button"
                  class="nb-btn primary"
                  :disabled="!view.draftQuestion.trim()"
                  @click="startInvestigation"
                >
                  Start investigation
                </button>
              </div>
              <div
                v-else
                class="nb-next-card"
              >
                <div>
                  <div class="nb-next-title">
                    Save question
                  </div>
                </div>
                <button
                  type="button"
                  class="nb-btn primary"
                  :disabled="!view.draftQuestion.trim()"
                  @click="saveEditedQuestion"
                >
                  Save question
                </button>
              </div>
            </template>
          </template>

          <!-- ============ EVIDENCE ============ -->
          <template v-else-if="view.step === 'evidence'">
            <div class="nb-main-head-row">
              <div>
                <h2
                  ref="stepHeadingRef"
                  class="nb-section-title"
                  tabindex="-1"
                >
                  Review the evidence
                </h2>
                <p class="nb-section-helper">
                  Check what the trace shows before choosing an explanation.
                </p>
              </div>
              <div class="nb-add-evidence-wrap">
                <button
                  type="button"
                  class="nb-btn small"
                  @click="addEvidenceMenuOpen = !addEvidenceMenuOpen"
                >
                  Add evidence
                  <svg
                    width="12"
                    height="12"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  ><path d="M6 9l6 6 6-6" /></svg>
                </button>
                <div
                  v-if="addEvidenceMenuOpen"
                  class="nb-menu"
                >
                  <button
                    type="button"
                    class="nb-menu-item"
                    :disabled="!findingOptions.length"
                    @click="openEvidenceForm('finding')"
                  >
                    From Findings
                  </button>
                  <button
                    type="button"
                    class="nb-menu-item"
                    :disabled="!props.cursorRange"
                    @click="openEvidenceForm('measurement')"
                  >
                    Current measurement
                  </button>
                  <button
                    type="button"
                    class="nb-menu-item"
                    @click="openEvidenceForm('note')"
                  >
                    Note
                  </button>
                </div>
              </div>
            </div>

            <div
              v-if="evidenceFormOpen"
              class="nb-add"
            >
              <div class="nb-add-row">
                <select
                  v-model="draft.type"
                  class="nb-input nb-type"
                >
                  <option
                    v-for="t in evidenceTypes"
                    :key="t"
                    :value="t"
                  >
                    {{ typeLabels[t] }}
                  </option>
                </select>
                <input
                  v-model="draft.title"
                  class="nb-input"
                  type="text"
                  placeholder="Evidence title"
                  @keydown.enter.prevent="addDraft"
                >
                <button
                  type="button"
                  class="nb-btn primary"
                  :disabled="!draft.title.trim()"
                  @click="addDraft"
                >
                  Add
                </button>
              </div>
              <textarea
                v-model="draft.note"
                class="nb-input nb-note"
                rows="2"
                placeholder="Note (optional)"
              />
              <div class="nb-add-refs">
                <label
                  v-if="props.cursorRange"
                  class="nb-chk"
                >
                  <input
                    v-model="draft.useRange"
                    type="checkbox"
                  >
                  Attach current cursor range
                  ({{ fmt(props.cursorRange.start) }} – {{ fmt(props.cursorRange.end) }})
                </label>
                <label
                  v-if="findingOptions.length"
                  class="nb-chk"
                >
                  Link finding
                  <select
                    v-model="draft.findingRuleId"
                    class="nb-input nb-ref-sel"
                  >
                    <option value="">
                      — none —
                    </option>
                    <option
                      v-for="f in findingOptions"
                      :key="f.rule_id"
                      :value="f.rule_id"
                    >{{ f.label }}</option>
                  </select>
                </label>
              </div>
            </div>

            <div
              v-for="it in sections.evidence.items"
              :key="it.bookmark_id"
              class="nb-ev-card"
              :class="{ stale: it.stale, broken: brokenIds.has(it.bookmark_id) }"
            >
              <label class="nb-ev-check">
                <input
                  type="checkbox"
                  :checked="view.selectedEvidenceIds.includes(it.bookmark_id)"
                  @change="toggleEvidenceSelected(it.bookmark_id)"
                >
              </label>
              <div class="nb-ev-body">
                <div class="nb-ev-top">
                  <span class="nb-ev-id">E{{ evidenceIndexById[it.bookmark_id] }}</span>
                  <input
                    :value="it.text"
                    class="nb-ev-title-input"
                    type="text"
                    @change="commit(updateBm(it.bookmark_id, { title: $event.target.value }))"
                  >
                </div>
                <div
                  v-if="cardMeta(it)"
                  class="nb-ev-value"
                >
                  {{ cardMeta(it) }}
                </div>
                <div class="nb-ev-source">
                  {{ cardSource(it) }} · {{ kindLabel(it.kind) }}
                  <span
                    v-if="it.stale"
                    class="nb-stale"
                  >⚠ stale</span>
                </div>
                <textarea
                  :value="it.note"
                  class="nb-ev-note"
                  rows="1"
                  placeholder="Explanation (your words)"
                  @change="commit(editExplanation(it.bookmark_id, $event.target.value))"
                />
                <div class="nb-ev-actions">
                  <!-- The Notebook is a full-screen modal over the timeline /
                       Statistics, so a "view source" navigation has to close it
                       first (its state is kept in the tab history and restored
                       when it is reopened). -->
                  <button
                    v-if="it.nav.jump != null || it.nav.range"
                    type="button"
                    class="nb-ev-action"
                    @click="emit('close'); onEvidenceJump(it.nav)"
                  >
                    View source
                  </button>
                  <button
                    v-if="it.nav.stats_metric"
                    type="button"
                    class="nb-ev-action"
                    @click="emit('close'); emit('open-statistics', it.nav.stats_metric)"
                  >
                    Open Statistics
                  </button>
                  <button
                    type="button"
                    class="nb-ev-action"
                    @click="emit('close'); emit('query-ai', { prompt: buildAskAboutEvidencePrompt(it) })"
                  >
                    Ask AI about this
                  </button>
                  <button
                    type="button"
                    class="nb-ev-action muted nb-ev-delete"
                    :title="`Delete evidence E${evidenceIndexById[it.bookmark_id]}`"
                    aria-label="Delete evidence"
                    @click="removeEvidenceWithConfirm(it.bookmark_id)"
                  >
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="1.8"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    ><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14M10 11v6M14 11v6" /></svg>
                  </button>
                  <button
                    type="button"
                    class="nb-ev-action muted"
                    @click="toggleExpanded(it.bookmark_id)"
                  >
                    Details
                    <svg
                      width="11"
                      height="11"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    ><path :d="view.expandedCardIds.includes(it.bookmark_id) ? 'M6 15l6-6 6 6' : 'M6 9l6 6 6-6'" /></svg>
                  </button>
                </div>

                <div
                  v-if="view.expandedCardIds.includes(it.bookmark_id)"
                  class="nb-ev-details"
                >
                  <div
                    v-if="header.trace"
                    class="detail"
                  >
                    <span class="k">Trace</span><span class="v">{{ header.trace }}</span>
                  </div>
                  <div
                    v-if="it.card && it.card.task"
                    class="detail"
                  >
                    <span class="k">Task / core</span><span class="v">{{ it.card.task }}<template v-if="it.card.core"> · {{ it.card.core }}</template></span>
                  </div>
                  <div class="detail">
                    <span class="k">Recorded scope</span><span class="v">{{ header.scope }}</span>
                  </div>
                  <div
                    v-if="it.card && it.card.created_at"
                    class="detail"
                  >
                    <span class="k">Timestamp</span><span class="v">{{ it.card.created_at }}</span>
                  </div>
                  <div class="detail">
                    <span class="k">Source</span><span class="v">{{ cardSource(it) }}</span>
                  </div>
                  <div class="detail">
                    <span class="k">Added</span><span class="v">{{ cardAuthor(it) }}</span>
                  </div>
                  <button
                    v-if="restorePlan(it)"
                    type="button"
                    class="nb-btn small"
                    title="This evidence was measured under a different scope"
                    @click="restoreConfirmFor = restoreConfirmFor === it.bookmark_id ? '' : it.bookmark_id"
                  >
                    Restore evidence scope…
                  </button>
                  <div
                    v-if="restoreConfirmFor === it.bookmark_id && restorePlan(it)"
                    class="nb-restore-confirm"
                  >
                    <div class="nb-restore-lead">
                      {{ restorePlan(it).summary }} Restoring will:
                    </div>
                    <ul class="nb-restore-changes">
                      <li
                        v-for="(c, ci) in restorePlan(it).changes"
                        :key="ci"
                      >
                        {{ c }}
                      </li>
                    </ul>
                    <div class="nb-restore-actions">
                      <button
                        type="button"
                        class="nb-btn small"
                        @click="restoreConfirmFor = ''"
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        class="nb-btn small primary"
                        @click="doRestoreScope(it)"
                      >
                        Restore scope
                      </button>
                    </div>
                  </div>
                  <div
                    v-if="restoredFor === it.bookmark_id"
                    class="nb-restore-done"
                  >
                    Scope restored.
                    <button
                      type="button"
                      class="nb-restore-undo"
                      @click="undoRestoreScope"
                    >
                      ↩ Undo
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <div class="nb-next-card">
              <div>
                <div class="nb-next-title">
                  {{ evidenceNextAction.label }}
                </div>
                <div
                  v-if="evidenceNextAction.reason"
                  class="nb-next-reason"
                >
                  {{ evidenceNextAction.reason }}
                </div>
              </div>
              <button
                type="button"
                class="nb-btn primary"
                :disabled="evidenceNextAction.id === 'review'"
                @click="onEvidenceNextAction"
              >
                {{ evidenceNextAction.label }}
              </button>
            </div>
          </template>

          <!-- ============ VERIFY ============ -->
          <template v-else-if="view.step === 'verify'">
            <div class="nb-main-head-row">
              <div>
                <h2
                  ref="stepHeadingRef"
                  class="nb-section-title"
                  tabindex="-1"
                >
                  Test possible explanations
                </h2>
                <p class="nb-section-helper">
                  Use evidence to support, contradict, or leave each explanation unresolved.
                </p>
              </div>
              <div class="nb-head-actions">
                <button
                  type="button"
                  class="nb-btn small"
                  @click="addExplanationOpen = !addExplanationOpen"
                >
                  Add explanation
                </button>
                <button
                  type="button"
                  class="nb-btn small"
                  :disabled="!!nbAiActionReason('draft_hypotheses', props.investigation, { aiEnabled: props.aiEnabled, hasSecondTrace: props.hasSecondTrace })"
                  :title="nbAiActionReason('draft_hypotheses', props.investigation, { aiEnabled: props.aiEnabled, hasSecondTrace: props.hasSecondTrace })"
                  @click="collaborate('draft_hypotheses')"
                >
                  Suggest explanations
                </button>
              </div>
            </div>

            <div
              v-if="addExplanationOpen"
              class="nb-add"
            >
              <div class="nb-add-row">
                <input
                  v-model="hypDraft.title"
                  class="nb-input"
                  type="text"
                  placeholder="Explanation title"
                  @keydown.enter.prevent="addExplanation"
                >
                <button
                  type="button"
                  class="nb-btn primary"
                  :disabled="!hypDraft.title.trim()"
                  @click="addExplanation"
                >
                  Add
                </button>
              </div>
              <textarea
                v-model="hypDraft.note"
                class="nb-input nb-note"
                rows="2"
                placeholder="Reasoning (optional)"
              />
            </div>

            <div
              v-for="it in sections.hypotheses.items"
              :key="it.bookmark_id"
              class="nb-exp-card"
            >
              <div class="nb-exp-top">
                <input
                  :value="it.text"
                  class="nb-exp-title-input"
                  type="text"
                  @change="commit(updateBm(it.bookmark_id, { title: $event.target.value }))"
                >
                <span
                  class="nb-exp-status"
                  :class="`h-${it.status}`"
                >{{ it.status }}</span>
              </div>
              <textarea
                :value="it.note"
                class="nb-exp-reason"
                rows="2"
                placeholder="Reasoning"
                @change="commit(updateBm(it.bookmark_id, { note: $event.target.value }))"
              />

              <div class="nb-exp-group">
                <div class="nb-exp-group-label">
                  Supporting evidence
                </div>
                <div
                  v-if="explanationLinks(it.bookmark_id, 'supports').length"
                  class="nb-exp-chips"
                >
                  <span
                    v-for="eid in explanationLinks(it.bookmark_id, 'supports')"
                    :key="eid"
                    class="nb-ev-chip"
                  >E{{ evidenceIndexById[eid] }}</span>
                </div>
                <span
                  v-else
                  class="nb-exp-hint"
                >None linked yet</span>
              </div>
              <div class="nb-exp-group">
                <div class="nb-exp-group-label">
                  Contradicting evidence
                </div>
                <div
                  v-if="explanationLinks(it.bookmark_id, 'contradicts').length"
                  class="nb-exp-chips"
                >
                  <span
                    v-for="eid in explanationLinks(it.bookmark_id, 'contradicts')"
                    :key="eid"
                    class="nb-ev-chip"
                  >E{{ evidenceIndexById[eid] }}</span>
                </div>
                <span
                  v-else
                  class="nb-exp-hint"
                >None linked yet</span>
              </div>
              <div class="nb-exp-group">
                <div class="nb-exp-group-label">
                  Checks to complete ({{ checksForExplanation(it.bookmark_id).length }})
                </div>
                <div
                  v-for="chk in checksForExplanation(it.bookmark_id)"
                  :key="chk.bookmark_id"
                  class="nb-check-card"
                >
                  <div class="nb-check-row">
                    <span class="k">Action</span><span class="v">{{ chk.text }}</span>
                  </div>
                  <div class="nb-check-row">
                    <span class="k">Why / expected</span>
                    <textarea
                      :value="chk.note"
                      class="nb-input nb-note"
                      rows="2"
                      @change="commit(updateBm(chk.bookmark_id, { note: $event.target.value }))"
                    />
                  </div>
                  <div
                    v-if="checkExecutionAction(chk)"
                    class="nb-check-row"
                  >
                    <span class="k">Execution</span>
                    <button
                      type="button"
                      class="nb-btn small"
                      @click="runCheckExecution(chk)"
                    >
                      {{ checkExecutionAction(chk).label }}
                    </button>
                  </div>
                  <div class="nb-check-row">
                    <span class="k">Outcome</span><span class="v"><span class="nb-outcome-pill">Not checked</span></span>
                  </div>
                </div>
                <span
                  v-if="!checksForExplanation(it.bookmark_id).length"
                  class="nb-exp-hint"
                >No checks added</span>
                <button
                  type="button"
                  class="nb-btn small"
                  style="margin-top: 6px"
                  @click="addCheckFor(it.bookmark_id)"
                >
                  Add a check
                </button>
              </div>

              <div class="nb-exp-actions">
                <button
                  type="button"
                  class="nb-btn small"
                  @click="linkPickerFor = linkPickerFor === it.bookmark_id ? '' : it.bookmark_id"
                >
                  Link evidence
                </button>
              </div>
              <div
                v-if="linkPickerFor === it.bookmark_id"
                class="nb-link-picker"
              >
                <select
                  v-model="linkPicker.evidenceId"
                  class="nb-input"
                >
                  <option value="">
                    Choose evidence…
                  </option>
                  <option
                    v-for="ev in sections.evidence.items"
                    :key="ev.bookmark_id"
                    :value="ev.bookmark_id"
                  >
                    E{{ evidenceIndexById[ev.bookmark_id] }} · {{ ev.text }}
                  </option>
                </select>
                <div class="nb-link-rel-row">
                  <label
                    v-for="rel in ['supports', 'contradicts', 'relates']"
                    :key="rel"
                    class="nb-chk"
                  >
                    <input
                      v-model="linkPicker.relation"
                      type="radio"
                      :value="rel"
                    >
                    {{ rel === 'relates' ? 'Related' : rel[0].toUpperCase() + rel.slice(1) }}
                  </label>
                </div>
                <button
                  type="button"
                  class="nb-btn small primary"
                  :disabled="!linkPicker.evidenceId"
                  @click="confirmLinkEvidence(it.bookmark_id)"
                >
                  Link
                </button>
              </div>
            </div>

            <div
              v-if="unassignedChecks.length"
              class="nb-card"
            >
              <p class="nb-card-title">
                Other checks
              </p>
              <div
                v-for="chk in unassignedChecks"
                :key="chk.bookmark_id"
                class="nb-check-card"
              >
                <div class="nb-check-row">
                  <span class="k">Action</span><span class="v">{{ chk.text }}</span>
                </div>
              </div>
            </div>

            <div class="nb-next-card">
              <div>
                <div class="nb-next-title">
                  {{ verifyNextAction.label }}
                </div>
              </div>
              <button
                type="button"
                class="nb-btn primary"
                :disabled="verifyNextAction.id === 'review' || verifyNextAction.id === 'none'"
                @click="onVerifyNextAction"
              >
                {{ verifyNextAction.label }}
              </button>
            </div>
          </template>

          <!-- ============ CONCLUSION ============ -->
          <template v-else-if="view.step === 'conclusion'">
            <h2
              ref="stepHeadingRef"
              class="nb-section-title"
              tabindex="-1"
            >
              Summarize what the evidence supports
            </h2>
            <p class="nb-section-helper">
              Write a conclusion you can export, even if some checks are still open.
            </p>

            <textarea
              v-model="view.draftConclusion"
              class="nb-conclusion-box"
              rows="6"
              placeholder="What does the evidence support? Leave blank until it does."
              @blur="commitConclusionDraft"
            />
            <div class="nb-ai-actions">
              <button
                type="button"
                class="nb-btn small"
                :disabled="!!nbAiActionReason('draft_conclusion', props.investigation, { aiEnabled: props.aiEnabled, hasSecondTrace: props.hasSecondTrace })"
                :title="nbAiActionReason('draft_conclusion', props.investigation, { aiEnabled: props.aiEnabled, hasSecondTrace: props.hasSecondTrace })"
                @click="collaborate('draft_conclusion')"
              >
                Draft conclusion
              </button>
              <button
                type="button"
                class="nb-btn small"
                :disabled="!props.aiEnabled"
                :title="props.aiEnabled ? '' : nbAiDisabledReason"
                @click="collaborate('review_investigation')"
              >
                Review conclusion
              </button>
            </div>

            <div
              v-for="chain in groundedChains"
              :key="chain.conclusion_id"
              class="nb-chain"
            >
              <strong>{{ chain.title }}</strong> ←
              <span
                v-for="(e, i) in chain.evidence"
                :key="e.id"
              >{{ i ? ' · ' : '' }}{{ typeLabels[e.type] || e.type }}: {{ e.title }}</span>
            </div>

            <div class="nb-card">
              <p class="nb-card-title">
                Cited evidence
              </p>
              <div
                v-if="sections.evidence.items.length"
                class="nb-exp-chips"
              >
                <span
                  v-for="ev in sections.evidence.items"
                  :key="ev.bookmark_id"
                  class="nb-ev-chip"
                >E{{ evidenceIndexById[ev.bookmark_id] }}</span>
              </div>
              <p
                v-else
                class="nb-meta-empty"
              >
                None yet.
              </p>
            </div>

            <div class="nb-card">
              <p class="nb-card-title">
                Unresolved checks ({{ unresolvedChecks.length }})
              </p>
              <div
                v-for="chk in unresolvedChecks"
                :key="chk.bookmark_id"
                class="nb-check-mini"
              >
                <span class="nb-outcome-pill">Not checked</span> {{ chk.text }}
              </div>
              <p
                v-if="!unresolvedChecks.length"
                class="nb-meta-empty"
              >
                None.
              </p>
            </div>

            <div class="nb-card">
              <p class="nb-card-title">
                Stale references
              </p>
              <p
                v-if="!brokenCount"
                class="nb-meta-empty"
              >
                None — every citation still resolves to current evidence.
              </p>
              <p
                v-else
                class="nb-sec-hint"
              >
                {{ brokenCount }} reference(s) no longer resolve — see Context details.
              </p>
            </div>

            <div class="nb-card">
              <p class="nb-card-title">
                Limitations
              </p>
              <p
                v-if="broken.stale_trace"
                class="nb-sec-hint warn"
              >
                ⚠ This investigation was recorded against a different trace than the one now open.
              </p>
              <p
                v-if="unresolvedChecks.length"
                class="nb-sec-hint warn"
              >
                ⚠ {{ unresolvedChecks.length }} unresolved check(s) — the export will label them explicitly.
              </p>
              <p
                v-if="!broken.stale_trace && !unresolvedChecks.length"
                class="nb-meta-empty"
              >
                None noted.
              </p>
            </div>

            <div class="nb-next-card">
              <div>
                <div class="nb-next-title">
                  Export report
                </div>
                <div class="nb-next-reason">
                  Exports this investigation as a JSON data file (Question, Scope, Hypotheses,
                  Evidence, Open checks, Conclusion) — re-importable from the ⋯ menu.
                  Use <strong>Preview report</strong> to read it here first.
                </div>
                <div class="nb-next-reason nb-next-reason-alt">
                  For a formatted HTML report you can open in a browser or share,
                  use the Statistics panel's <strong>Export HTML</strong> — it bundles
                  the statistics tables and the Analysis Findings for the current scope.
                </div>
              </div>
              <div style="display: flex; align-items: center; gap: 12px">
                <button
                  type="button"
                  class="nb-link-btn"
                  @click="previewOpen = !previewOpen"
                >
                  Preview report
                </button>
                <button
                  type="button"
                  class="nb-btn primary"
                  @click="exportJson"
                >
                  Export report
                </button>
              </div>
            </div>
            <div
              v-if="previewOpen"
              class="nb-preview"
            >
              <div
                v-for="sec in sectionList"
                :key="sec.id"
                class="nb-preview-section"
              >
                <strong>{{ sec.title }}</strong>
                <p
                  v-if="!sec.items.length"
                  class="nb-meta-empty"
                >
                  (none)
                </p>
                <ul v-else>
                  <li
                    v-for="(it, i) in sec.items"
                    :key="i"
                  >
                    {{ it.text }}
                  </li>
                </ul>
              </div>
            </div>
          </template>
        </div>

        <!-- AI assistance side column -->
        <div
          v-if="props.aiEnabled"
          class="nb-side-col"
        >
          <!-- §10 — AI proposal, reviewed and select-and-added right here -->
          <div
            v-if="hasInlineProposal"
            class="nb-card nb-proposal-card"
          >
            <div class="nb-assist-heading">
              <svg
                width="15"
                height="15"
                viewBox="0 0 24 24"
                fill="var(--accent)"
              ><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3z" /></svg>
              AI proposal
            </div>
            <p
              v-if="proposalReview.summary"
              class="nb-proposal-summary"
            >
              {{ proposalReview.summary }}
            </p>
            <ul
              v-if="proposalReview.notes.length"
              class="nb-proposal-notes"
            >
              <li
                v-for="(n, ni) in proposalReview.notes"
                :key="ni"
              >
                {{ n }}
              </li>
            </ul>

            <p
              v-if="!proposalReview.ok && !proposalReview.summary && !proposalReview.notes.length"
              class="nb-assist-body"
            >
              Nothing in this suggestion applies to the current investigation.
            </p>

            <template v-if="proposalReview.ok">
              <div
                v-for="grp in proposalGroupList"
                :key="grp.id"
                class="nb-prop-group"
              >
                <div class="nb-prop-group-label">
                  {{ grp.label }}
                </div>
                <label
                  v-for="op in grp.ops"
                  :key="op.index"
                  class="nb-prop-op"
                  :class="{ confirm: op.status === 'needs_confirmation' }"
                >
                  <input
                    type="checkbox"
                    :checked="proposalSel.has(op.index)"
                    @change="toggleProposalOp(op.index)"
                  >
                  <span class="nb-prop-op-body">
                    <span class="nb-prop-op-line">{{ proposalOpSummary(op) }}</span>
                    <span
                      v-if="proposalSourceRefs(op).length"
                      class="nb-prop-sources"
                    >
                      <span class="nb-prop-sources-label">from</span>
                      <span
                        v-for="rid in proposalSourceRefs(op)"
                        :key="rid"
                        class="nb-prop-src"
                      >{{ rid }}</span>
                    </span>
                    <span
                      v-if="op.status === 'needs_confirmation'"
                      class="nb-prop-confirm"
                    >
                      <input
                        type="checkbox"
                        :checked="proposalConfirm.has(op.index)"
                        @change="toggleProposalConfirm(op.index)"
                      >
                      Confirm — {{ op.reason }}
                    </span>
                    <span
                      v-else-if="op.reason"
                      class="nb-prop-note"
                    >{{ op.reason }}</span>
                  </span>
                </label>
              </div>
            </template>

            <div
              v-if="proposalGroups && proposalGroups.rejected.length"
              class="nb-prop-group rejected"
            >
              <div class="nb-prop-group-label">
                Not applicable ({{ proposalGroups.rejected.length }})
              </div>
              <div
                v-for="op in proposalGroups.rejected"
                :key="op.index"
                class="nb-prop-rejected"
              >
                {{ proposalOpSummary(op) }} — {{ op.reason }}
              </div>
            </div>

            <p
              v-if="proposalReview.ok && (proposalModel.model || proposalModel.provider)"
              class="nb-prop-model"
            >
              Proposed by {{ proposalModel.provider || 'AI' }}<template v-if="proposalModel.model">
                · {{ proposalModel.model }}
              </template>. Added cards keep this provenance.
            </p>

            <div class="nb-prop-actions">
              <button
                type="button"
                class="nb-btn small"
                @click="dismissProposal"
              >
                Dismiss
              </button>
              <span class="nb-prop-spacer" />
              <template v-if="proposalReview.ok">
                <button
                  type="button"
                  class="nb-btn small"
                  :disabled="!proposalApplicableCount"
                  @click="submitProposal(false)"
                >
                  Add selected ({{ proposalApplicableCount }})
                </button>
                <button
                  type="button"
                  class="nb-btn small primary"
                  @click="submitProposal(true)"
                >
                  Add all
                </button>
              </template>
            </div>
          </div>

          <div class="nb-card nb-assist-card">
            <div class="nb-assist-heading">
              <svg
                width="15"
                height="15"
                viewBox="0 0 24 24"
                fill="var(--accent)"
              ><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3z" /></svg>
              AI assistance
            </div>

            <template v-if="props.aiRequestState.busy">
              <p class="nb-assist-body">
                {{ props.aiRequestState.status || 'Working…' }}
              </p>
              <button
                type="button"
                class="nb-btn small"
                @click="emit('cancel-ai-request')"
              >
                Cancel request
              </button>
            </template>
            <template v-else-if="props.hasPendingProposal && !hasInlineProposal">
              <p class="nb-assist-body">
                1 pending suggestion — see the review panel.
              </p>
            </template>
            <template v-else-if="view.step === 'question'">
              <template v-if="props.refineSuggestion">
                <div class="nb-suggestion">
                  <span class="nb-suggestion-label">Revise question</span>
                  <p class="nb-suggestion-text">
                    {{ props.refineSuggestion }}
                  </p>
                  <button
                    type="button"
                    class="nb-btn small primary"
                    @click="useRefinedQuestion"
                  >
                    Use this question
                  </button>
                </div>
              </template>
              <template v-else>
                <p class="nb-assist-body">
                  AI can help you word a clearer, more specific question. This step never requires AI.
                </p>
                <button
                  type="button"
                  class="nb-btn small"
                  @click="collaborate('refine_question')"
                >
                  Help refine question
                </button>
              </template>
            </template>
            <template v-else-if="view.step === 'evidence'">
              <p class="nb-assist-body">
                {{ sections.evidence.items.length }} evidence item(s), {{ view.selectedEvidenceIds.length }} selected.
              </p>
              <button
                type="button"
                class="nb-btn small primary"
                :disabled="props.aiRequestState.busy"
                @click="collaborate('gather_evidence')"
              >
                Gather evidence with AI
              </button>
              <p class="nb-assist-body">
                Calls trace tools across several rounds, then proposes measured
                evidence cards for you to review and add.
              </p>
            </template>
            <template v-else-if="view.step === 'verify'">
              <p class="nb-assist-body">
                {{ unresolvedChecks.length }} open check(s) across {{ sections.hypotheses.items.length }} explanation(s).
              </p>
              <button
                type="button"
                class="nb-btn small"
                :disabled="!!nbAiActionReason('draft_hypotheses', props.investigation, { aiEnabled: props.aiEnabled, hasSecondTrace: props.hasSecondTrace })"
                @click="collaborate('draft_hypotheses')"
              >
                Suggest explanations
              </button>
            </template>
            <template v-else-if="view.step === 'conclusion'">
              <p class="nb-assist-body">
                {{ props.aiRequestState.status || 'Ask for a review to see gaps and contradictions here.' }}
              </p>
              <button
                type="button"
                class="nb-btn small"
                @click="collaborate('review_investigation')"
              >
                Review investigation
              </button>
            </template>

            <!-- The model answered in prose (no structured proposal). Present it
                 as demo-style titled sections + bullets, not a raw text dump —
                 the full exchange lives in the AI Assistant panel. -->
            <div
              v-if="stepAiReplyBlocks.length && !hasInlineProposal && !props.aiRequestState.busy"
              class="nb-assist-note"
            >
              <span class="nb-assist-note-label">AI reply</span>
              <div
                v-for="(blk, bi) in stepAiReplyBlocks"
                :key="bi"
                class="nb-assist-note-block"
              >
                <p
                  v-if="blk.title"
                  class="nb-assist-note-title"
                >
                  {{ blk.title }}
                </p>
                <ul
                  v-if="blk.items.length"
                  class="nb-assist-note-list"
                >
                  <li
                    v-for="(it, ii) in blk.items"
                    :key="ii"
                  >
                    {{ it }}
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>
        <div
          v-else
          class="nb-side-col nb-side-col-disabled"
        >
          AI is off — enable it in Settings → AI.
        </div>
      </div>

      <!-- Footer -->
      <div class="nb-footer">
        <span class="nb-save-state">Changes kept in this session</span>
        <div class="nb-footer-actions">
          <button
            type="button"
            class="nb-icon-btn"
            :disabled="!historyState.can_undo"
            title="Undo (notebook)"
            @click="emit('undo')"
          >
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linecap="round"
              stroke-linejoin="round"
            ><path d="M9 7L4 12l5 5" /><path d="M4 12h10a6 6 0 000-12" /></svg>
          </button>
          <button
            type="button"
            class="nb-icon-btn"
            :disabled="!historyState.can_redo"
            title="Redo (notebook)"
            @click="emit('redo')"
          >
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linecap="round"
              stroke-linejoin="round"
            ><path d="M15 7l5 5-5 5" /><path d="M20 12H10a6 6 0 010-12" /></svg>
          </button>
          <span class="nb-footer-sep" />
          <button
            type="button"
            class="nb-btn small"
            :disabled="stepIndex === 0"
            @click="goPrevStep"
          >
            ← Back
          </button>
          <button
            type="button"
            class="nb-btn small"
            :disabled="stepIndex === STEP_ORDER.length - 1"
            @click="goNextStep"
          >
            Next →
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import {
  BOOKMARK_TYPE_LABELS,
  EVIDENCE_BOOKMARK_TYPES,
  EVIDENCE_KIND_LABELS,
  NB_STATUS_CLOSED,
  NOTEBOOK_STATUS_LABELS,
  addBookmark,
  conclusionEvidenceChains,
  detectBrokenReferences,
  dumpInvestigation,
  investigationHeader,
  investigationSections,
  linkBookmarks,
  loadInvestigation,
  newInvestigation,
  removeBookmark,
  setConclusion,
  setStatus,
  topFindingsForStart,
  updateBookmark,
  updateEvidenceExplanation,
  evidenceScopeRestorePlan,
} from '../utils/investigationNotebook.js'
import {
  NB_AI_DISABLED_REASON,
  nbAiActionReason,
  collaborateContext,
  collaborateDigest,
  parseReplyBlocks,
  validateProposal,
  proposalDiff,
} from '../utils/investigationAi.js'

const props = defineProps({
  investigation: { type: Object, required: true },
  history: { type: Object, default: () => ({ stack: [], index: -1 }) },
  findings: { type: Array, default: () => [] },
  trace: { type: Object, default: null },
  traceFileName: { type: String, default: '' },
  cursorRange: { type: Object, default: null },
  formatNs: { type: Function, default: null },
  aiEnabled: { type: Boolean, default: false },
  hasSecondTrace: { type: Boolean, default: false },
  aiRequestState: { type: Object, default: () => ({ busy: false, error: '', status: '' }) },
  hasPendingProposal: { type: Boolean, default: false },
  // Raw `{ schema, operations[] }` proposal from the last collaborate reply.
  // Reviewed and select-and-added inline in the right panel (no separate modal).
  aiProposal: { type: Object, default: null },
  allowOtherTrace: { type: Boolean, default: false },
  refineSuggestion: { type: String, default: '' },
  // { step, text } — the plain-text reply from the last collaborate() request
  // made from this dialog, so it's visible right here even though the chat
  // bubble itself lives in the AI Assistant panel behind this modal.
  lastAiReply: { type: Object, default: null },
})

const emit = defineEmits([
  'close', 'update', 'undo', 'redo', 'restore', 'jump-range', 'open-statistics',
  'export-evidence-package', 'scaffold', 'collaborate',
  'restore-evidence-scope', 'undo-scope-restore', 'query-ai', 'focus-ai-panel',
  'cancel-ai-request', 'apply-proposal', 'dismiss-proposal',
])

const STEP_ORDER = ['question', 'evidence', 'verify', 'conclusion']
const STEP_LABELS = {
  question: 'Question', evidence: 'Evidence', verify: 'Verify', conclusion: 'Conclusion',
}

const fileInput = ref(null)
const stepHeadingRef = ref(null)
const shellRef = ref(null)
const typeLabels = BOOKMARK_TYPE_LABELS
const evidenceTypes = EVIDENCE_BOOKMARK_TYPES
const nbAiDisabledReason = NB_AI_DISABLED_REASON

// Transient view state — never persisted (no loadInvestigation/dumpInvestigation
// round trip, no sessionStore/workspace involvement). §9 NotebookViewState,
// Vue-idiomatic: named drafts instead of a generic draftByField map.
const view = reactive({
  step: 'question',
  selectedEvidenceIds: [],
  expandedCardIds: [],
  draftQuestion: '',
  draftConclusion: '',
})

const moreMenuOpen = ref(false)
const historyOpen = ref(false)
const restoreConfirmFor = ref('')
const restoredFor = ref('')
const contextDetailsOpen = ref(false)
const isCompactStepNav = ref(false)
const stepSelectorOpen = ref(false)
const questionEditing = ref(false)
const selectedFindingId = ref('')
const addEvidenceMenuOpen = ref(false)
const evidenceFormOpen = ref(false)
const addExplanationOpen = ref(false)
const linkPickerFor = ref('')
const previewOpen = ref(false)
// Moveable window: null = default centered (the .dialog-overlay flex
// centers it); once dragged, an explicit fixed {left, top} takes over.
// Resets to centered every time the dialog is reopened (it fully unmounts
// on close, per App.vue's v-if), so this never needs explicit reset logic.
const shellPos = ref(null)
const dragging = ref(false)
let dragState = null
let mq = null

const draft = reactive({
  type: 'supporting', title: '', note: '', useRange: false, findingRuleId: '',
})
const hypDraft = reactive({ title: '', note: '' })
const linkPicker = reactive({ evidenceId: '', relation: 'supports' })

const inv = computed(() => loadInvestigation(props.investigation))

const historyState = computed(() => {
  const stack = props.history?.stack || []
  const idx = Number(props.history?.index ?? -1)
  return {
    can_undo: idx > 0,
    can_redo: idx >= 0 && idx < stack.length - 1,
    count: stack.length,
    index: idx,
  }
})

const findingOptions = computed(() => {
  const seen = new Set()
  const out = []
  for (const f of props.findings || []) {
    const rid = String(f.rule_id || f.ruleId || f.id || '').trim()
    if (!rid || seen.has(rid)) continue
    seen.add(rid)
    out.push({ rule_id: rid, label: `${f.severity || 'info'} · ${f.title || rid}` })
  }
  return out
})
const startFindings = computed(() => topFindingsForStart(props.findings, 3))

const broken = computed(() =>
  detectBrokenReferences(props.investigation, {
    trace: props.trace,
    knownRuleIds: findingOptions.value.map((f) => f.rule_id),
  }))
const brokenIds = computed(() => new Set(broken.value.issues.map((i) => i.bookmark_id)))
const brokenCount = computed(() => broken.value.issues.length + (broken.value.stale_trace ? 1 : 0))
const groundedChains = computed(() =>
  conclusionEvidenceChains(props.investigation).filter((c) => c.grounded))

const sectionList = computed(() => investigationSections(props.investigation, { broken: broken.value }))
const sections = computed(() => Object.fromEntries(sectionList.value.map((s) => [s.id, s])))
const header = computed(() => investigationHeader(props.investigation, { broken: broken.value }))

const evidenceIndexById = computed(() => {
  const map = {}
  sections.value.evidence.items.forEach((it, i) => { map[it.bookmark_id] = i + 1 })
  return map
})
const unresolvedChecks = computed(() => sections.value.open_checks.items.filter((x) => x.source === 'verification'))

// The last AI reply, shown only on the step it was requested from — so
// "Check evidence with AI" / "Suggest explanations" / "Review investigation"
// surface their answer right on this card, without requiring the user to
// close the Notebook to read it.
const stepAiReplyText = computed(() => {
  const reply = props.lastAiReply
  if (!reply || reply.step !== view.step || !reply.text) return ''
  return reply.text
})

// Present a prose AI reply as demo-style titled sections + bullets instead of
// one raw pre-wrapped blob (parser lives in investigationAi.js, shared with
// the Python side). Defensive: if a structured proposal leaked through as
// prose (extraction failed upstream), strip the ```json block and the
// btfnext:/btfstats: "next step" links so the card never shows machine noise.
const stepAiReplyBlocks = computed(() => {
  const raw = stepAiReplyText.value
  if (!raw) return []
  const cleaned = raw
    .replace(/```(?:json)?\s*[\s\S]*?```/gi, '')
    .split('\n')
    .filter((ln) => !/\]\((?:btfnext|btfstats):/i.test(ln))
    .join('\n')
  return parseReplyBlocks(cleaned)
})

// --- inline AI proposal review (§10) — shown in the right panel, no modal ---
// The shared validateProposal / proposalDiff give the accept/confirm rules;
// this component is the only surface that renders them.
const proposalReview = computed(() =>
  props.aiProposal
    ? validateProposal(props.investigation, props.aiProposal, { allowOtherTrace: props.allowOtherTrace })
    : null)
const proposalGroups = computed(() =>
  proposalReview.value ? proposalDiff(props.investigation, proposalReview.value) : null)
const hasInlineProposal = computed(() => !!proposalReview.value)
const proposalModel = computed(() => proposalReview.value?.model || {})
const proposalGroupList = computed(() => {
  const s = proposalGroups.value?.by_section
  if (!s) return []
  return [
    { id: 'hypotheses', label: 'Hypotheses', ops: s.hypotheses },
    { id: 'evidence', label: 'Evidence', ops: s.evidence },
    { id: 'conclusion', label: 'Conclusion', ops: s.conclusion },
    { id: 'status', label: 'Status', ops: s.status },
    { id: 'links', label: 'Links', ops: s.links },
  ].filter((g) => g.ops.length)
})

const proposalSel = reactive(new Set())
const proposalConfirm = reactive(new Set())
const proposalBump = ref(0)

watch(proposalReview, (v) => {
  proposalSel.clear()
  proposalConfirm.clear()
  for (const op of v?.operations || []) {
    if (op.status === 'ok') proposalSel.add(op.index)
  }
  proposalBump.value++
}, { immediate: true })

const proposalApplicableCount = computed(() => {
  void proposalBump.value
  return (proposalReview.value?.operations || []).filter((op) => {
    if (!proposalSel.has(op.index)) return false
    if (op.status === 'ok') return true
    if (op.status === 'needs_confirmation') return proposalConfirm.has(op.index)
    return false
  }).length
})

function toggleProposalOp(i) {
  if (proposalSel.has(i)) proposalSel.delete(i)
  else proposalSel.add(i)
  proposalBump.value++
}
function toggleProposalConfirm(i) {
  if (proposalConfirm.has(i)) proposalConfirm.delete(i)
  else { proposalConfirm.add(i); proposalSel.add(i) }
  proposalBump.value++
}
function proposalSourceRefs(op) {
  const ids = Array.isArray(op.evidence_ids) ? op.evidence_ids : []
  return ids.map(String).map((s) => s.trim()).filter(Boolean)
}
function proposalBmTitle(id) {
  const b = inv.value.bookmarks.find((x) => String(x.id) === String(id))
  return b ? b.title : id
}
function proposalOpSummary(op) {
  const role = String(op.role || op.type || '')
  if (op.op === 'add') {
    const label = BOOKMARK_TYPE_LABELS[role] || role || 'evidence'
    return `Add ${label}: “${op.title || '(untitled)'}”`
  }
  if (op.op === 'update') {
    if ('conclusion' in (op.changes || {})) return 'Replace the conclusion text'
    return `Edit explanation of “${proposalBmTitle(op.bookmark_id)}”`
  }
  if (op.op === 'link') {
    return `Link “${proposalBmTitle(op.from)}” —${op.relation || 'relates'}→ “${proposalBmTitle(op.to)}”`
  }
  if (op.op === 'change_status') {
    const s = op.status_value || op.status
    return `Set status to ${NOTEBOOK_STATUS_LABELS[s] || s}`
  }
  if (op.op === 'remove') return `Remove “${proposalBmTitle(op.bookmark_id)}”`
  return op.op || 'operation'
}
function dismissProposal() { emit('dismiss-proposal') }
function submitProposal(acceptAll) {
  const v = proposalReview.value
  if (!v) return
  if (acceptAll) {
    emit('apply-proposal', {
      validated: v,
      acceptIndices: null,
      confirmedIndices: (v.operations || [])
        .filter((op) => op.status === 'needs_confirmation').map((op) => op.index),
      acceptAll: true,
    })
  } else {
    emit('apply-proposal', {
      validated: v,
      acceptIndices: [...proposalSel],
      confirmedIndices: [...proposalConfirm],
      acceptAll: false,
    })
  }
}

const investigationHasContent = computed(() =>
  inv.value.bookmarks.length > 0
  || !!String(inv.value.conclusion || '').trim()
  || (inv.value.unresolved_questions || []).length > 0)

const stepIndex = computed(() => STEP_ORDER.indexOf(view.step))
const stepDone = computed(() => ({
  question: investigationHasContent.value,
  evidence: sections.value.evidence.items.length > 0,
  verify: sections.value.hypotheses.items.length > 0,
  conclusion: !!String(inv.value.conclusion || '').trim(),
}))

const contextDigest = computed(() => collaborateDigest(collaborateContext(props.investigation, { broken: broken.value })))

// --- next-action resolvers -------------------------------------------
function resolveEvidenceNextAction() {
  if (props.aiRequestState.busy) return { id: 'cancel', label: 'Cancel request', reason: '' }
  if (props.hasPendingProposal) return { id: 'review', label: 'Review suggestions', reason: 'AI suggestions are ready for review.' }
  const evidenceCount = sections.value.evidence.items.length
  if (evidenceCount === 0) return { id: 'add', label: 'Add evidence', reason: 'Add at least one item before checking with AI.' }
  const selectedCount = view.selectedEvidenceIds.length
  if (props.aiEnabled && selectedCount > 0) {
    return { id: 'check', label: 'Check evidence with AI', reason: `${selectedCount} of ${evidenceCount} item(s) selected.` }
  }
  if (props.aiEnabled && selectedCount === 0) {
    return { id: 'select', label: 'Select all evidence', reason: 'Or tick just the items you want to send to AI.' }
  }
  return { id: 'explain', label: 'Add an explanation', reason: 'Move to Verify to test a possible explanation.' }
}
const evidenceNextAction = computed(resolveEvidenceNextAction)

function onEvidenceNextAction() {
  const a = evidenceNextAction.value
  if (a.id === 'cancel') emit('cancel-ai-request')
  else if (a.id === 'review') { /* the proposal card is already in the side panel */ }
  else if (a.id === 'add') { addEvidenceMenuOpen.value = true }
  else if (a.id === 'check') collaborate('review_investigation', { selectedEvidenceIds: view.selectedEvidenceIds })
  else if (a.id === 'select') {
    // One click ticks every evidence item; the resolver then flips to
    // "Check evidence with AI". Untick individually to narrow it.
    view.selectedEvidenceIds = sections.value.evidence.items.map((x) => x.bookmark_id)
  }
  else if (a.id === 'explain') goToStep('verify')
}

const verifyNextAction = computed(() => {
  if (props.aiRequestState.busy) return { id: 'cancel', label: 'Cancel request' }
  if (props.hasPendingProposal) return { id: 'review', label: 'Review suggestions' }
  for (const it of sections.value.hypotheses.items) {
    for (const chk of checksForExplanation(it.bookmark_id)) {
      if (checkExecutionAction(chk)) return { id: 'run', label: checkExecutionAction(chk).label, check: chk }
    }
  }
  return { id: 'none', label: 'Choose a check' }
})
function onVerifyNextAction() {
  const a = verifyNextAction.value
  if (a.id === 'cancel') emit('cancel-ai-request')
  else if (a.id === 'run' && a.check) runCheckExecution(a.check)
}

// --- header / more menu ------------------------------------------------
// A pending AI proposal was validated against the investigation it was asked
// from — drop it whenever that investigation is replaced, restored, or closed
// so it can't be applied to unrelated state.
function restoreSnapshot(index) {
  historyOpen.value = false
  emit('dismiss-proposal')
  emit('restore', index)
}
function closeInvestigation() {
  if (!window.confirm('Close this investigation? You can reopen it later from the workspace.')) return
  emit('dismiss-proposal')
  commit(setStatus(props.investigation, NB_STATUS_CLOSED))
}
// Q1 fix: there was no way to clear the current notebook and start over —
// only "Close investigation" (marks it closed, keeps all content). This
// replaces it with a genuinely blank investigation in one undo step, so an
// accidental click is a single Undo away.
function startNewInvestigation() {
  if (investigationHasContent.value &&
      !window.confirm('Start a new investigation? The current one will be replaced (Undo restores it).')) return
  emit('dismiss-proposal')
  commit(newInvestigation({
    title: '',
    traceIdentity: props.investigation.trace_identity,
    analysisRange: props.investigation.analysis_range,
  }))
  view.step = 'question'
  view.selectedEvidenceIds = []
  view.expandedCardIds = []
  view.draftQuestion = ''
  view.draftConclusion = ''
  questionEditing.value = true
  selectedFindingId.value = ''
}

function fmt(ns) {
  const f = props.formatNs || ((v) => String(Math.trunc(v)))
  return f(ns)
}
function commit(nextInv) {
  emit('update', nextInv)
}

// Tags every collaborate request with the step it was asked from, so the
// reply (App.vue's :last-ai-reply prop) can be shown back on that same
// step's AI assistance card instead of only being visible in the AI
// Assistant panel — which sits behind this full-screen modal.
function collaborate(action, extra = {}) {
  emit('collaborate', { action, sourceStep: view.step, ...extra })
}

// --- Question step -------------------------------------------------------
function startEditQuestion() {
  view.draftQuestion = inv.value.title || ''
  questionEditing.value = true
}
function saveEditedQuestion() {
  commit(loadInvestigation({ ...inv.value, title: view.draftQuestion.trim() }))
  questionEditing.value = false
}
function startInvestigation() {
  if (!view.draftQuestion.trim()) return
  // §4 — one undoable transaction: title + (optionally) the selected
  // finding as the first evidence, committed in a single emit('update').
  let next = loadInvestigation({ ...props.investigation, title: view.draftQuestion.trim() })
  const f = startFindings.value.find(
    (x) => (x.rule_id || x.ruleId || x.id) === selectedFindingId.value)
  if (f) {
    const refs = [{ kind: 'finding', rule_id: String(f.rule_id || f.ruleId || f.id), label: String(f.title || f.rule_id) }]
    if (f.affected_range && f.affected_range.start != null) refs.push({ kind: 'range', range: f.affected_range })
    const metric = String(f.inspect || f.inspect_href || '').trim()
    if (metric) refs.push({ kind: 'metric', metric })
    next = addBookmark(next, {
      type: 'observation',
      title: String(f.title || f.observation || f.rule_id),
      note: String(f.text || f.impact || ''),
      refs,
    })
  }
  commit(next)
  questionEditing.value = false
  goToStep('evidence')
}
function useRefinedQuestion() {
  if (!props.refineSuggestion) return
  commit(loadInvestigation({ ...inv.value, title: props.refineSuggestion }))
}

// --- Evidence step ---------------------------------------------------
function openEvidenceForm(kind) {
  addEvidenceMenuOpen.value = false
  evidenceFormOpen.value = true
  if (kind === 'measurement') draft.useRange = true
  if (kind === 'finding') draft.type = 'supporting'
}
function toggleEvidenceSelected(id) {
  view.selectedEvidenceIds = view.selectedEvidenceIds.includes(id)
    ? view.selectedEvidenceIds.filter((x) => x !== id)
    : [...view.selectedEvidenceIds, id]
}
function toggleExpanded(id) {
  view.expandedCardIds = view.expandedCardIds.includes(id)
    ? view.expandedCardIds.filter((x) => x !== id)
    : [...view.expandedCardIds, id]
}
function addDraft() {
  if (!draft.title.trim()) return
  const refs = []
  if (draft.useRange && props.cursorRange) {
    refs.push({ kind: 'range', range: { start: props.cursorRange.start, end: props.cursorRange.end } })
  }
  if (draft.findingRuleId) refs.push({ kind: 'finding', rule_id: draft.findingRuleId })
  commit(addBookmark(props.investigation, {
    type: draft.type, title: draft.title.trim(), note: draft.note, refs,
  }))
  draft.title = ''
  draft.note = ''
  draft.findingRuleId = ''
  draft.useRange = false
  evidenceFormOpen.value = false
}
function removeEvidenceWithConfirm(id) {
  if (!window.confirm('Delete this evidence item? (Undo restores it.)')) return
  commit(removeBookmark(props.investigation, id))
  view.selectedEvidenceIds = view.selectedEvidenceIds.filter((x) => x !== id)
}
function updateBm(id, changes) {
  return updateBookmark(props.investigation, id, changes)
}
function editExplanation(id, note) {
  return updateEvidenceExplanation(props.investigation, id, note)
}
function kindLabel(kind) {
  if (!kind || kind === 'note') return EVIDENCE_KIND_LABELS['']
  return EVIDENCE_KIND_LABELS[kind] || kind
}
function cardSource(it) {
  const s = it.card?.source
  if (s) return s
  return it.role === 'contradicting' ? 'Contradicting' : it.role === 'supporting' ? 'Supporting' : 'Observation'
}
function cardAuthor(it) {
  const a = it.card?.author || 'user'
  return a === 'ai' ? 'AI' : a === 'btfviewer' ? 'BTFViewer' : 'User'
}
function cardMeta(it) {
  const c = it.card || {}
  const bits = []
  if (c.value != null && c.value !== '') bits.push(`${c.value}${c.unit ? ' ' + c.unit : ''}`)
  if (c.trace_id) bits.push(`trace ${c.trace_id}`)
  return bits.join(' · ')
}
function onEvidenceJump(nav) {
  if (nav.range) emit('jump-range', { start: nav.range[0], end: nav.range[1] })
  else if (nav.jump != null) emit('jump-range', { start: nav.jump, end: nav.jump })
}
function restorePlan(it) {
  return evidenceScopeRestorePlan(it.card, { currentScope: props.cursorRange, fmt })
}
function doRestoreScope(it) {
  const plan = restorePlan(it)
  restoreConfirmFor.value = ''
  if (!plan) return
  emit('restore-evidence-scope', { start: plan.start, end: plan.end })
  restoredFor.value = it.bookmark_id
}
function undoRestoreScope() {
  emit('undo-scope-restore')
  restoredFor.value = ''
}
function buildAskAboutEvidencePrompt(it) {
  const meta = cardMeta(it)
  return `About this Notebook evidence item — "${it.text}"${meta ? ` (${meta})` : ''}`
    + `${it.note ? `: ${it.note}` : ''}. What else should I check?`
}

// --- Verify step -------------------------------------------------------
function addExplanation() {
  if (!hypDraft.title.trim()) return
  commit(addBookmark(props.investigation, {
    type: 'hypothesis', title: hypDraft.title.trim(), note: hypDraft.note,
  }))
  hypDraft.title = ''
  hypDraft.note = ''
  addExplanationOpen.value = false
}
function explanationLinks(explanationId, relation) {
  return (inv.value.links || [])
    .filter((l) => l.relation === relation && (l.to === explanationId || l.from === explanationId))
    .map((l) => (l.to === explanationId ? l.from : l.to))
}
function linkedCheckIds(explanationId) {
  return new Set(explanationLinks(explanationId, 'verifies'))
}
function checksForExplanation(explanationId) {
  const ids = linkedCheckIds(explanationId)
  return unresolvedChecks.value.filter((c) => ids.has(c.bookmark_id))
}
const unassignedChecks = computed(() => {
  const linked = new Set()
  for (const it of sections.value.hypotheses.items) {
    for (const id of linkedCheckIds(it.bookmark_id)) linked.add(id)
  }
  return unresolvedChecks.value.filter((c) => !linked.has(c.bookmark_id))
})
function addCheckFor(explanationId) {
  const title = window.prompt('New check — what will you do?', '')
  if (title == null || !title.trim()) return
  let next = addBookmark(props.investigation, { type: 'verification', title: title.trim() })
  const newId = next.bookmarks[next.bookmarks.length - 1].id
  next = linkBookmarks(next, newId, explanationId, 'verifies')
  commit(next)
}
function checkExecutionAction(chk) {
  for (const r of chk.refs || []) {
    if (r.kind === 'range' && r.range) return { label: 'View timeline', range: r.range }
    if (r.kind === 'metric' && r.metric) return { label: 'Open Statistics', metric: r.metric }
  }
  return null
}
function runCheckExecution(chk) {
  const a = checkExecutionAction(chk)
  if (!a) return
  if (a.range) emit('jump-range', { start: a.range.start, end: a.range.end })
  else if (a.metric) emit('open-statistics', a.metric)
}
function confirmLinkEvidence(explanationId) {
  if (!linkPicker.evidenceId) return
  commit(linkBookmarks(props.investigation, linkPicker.evidenceId, explanationId, linkPicker.relation))
  linkPickerFor.value = ''
  linkPicker.evidenceId = ''
  linkPicker.relation = 'supports'
}

// --- Conclusion step ---------------------------------------------------
function commitConclusionDraft() {
  const current = String(inv.value.conclusion || '')
  if (view.draftConclusion.trim() === current.trim()) return
  commit(setConclusion(props.investigation, view.draftConclusion))
}

// --- header actions (export / import / evidence package) ---------------
function exportJson() {
  const base = (props.traceFileName || 'investigation').replace(/\.btf(\.gz)?$/i, '')
  const blob = new Blob([dumpInvestigation(props.investigation)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${base}-investigation.json`
  a.click()
  URL.revokeObjectURL(url)
}
function emitEvidencePackage() {
  const question = window.prompt(
    'Question the AI evidence package should answer:',
    props.investigation?.title || '',
  )
  if (question == null) return
  emit('export-evidence-package', { question: String(question).trim() })
}
async function onImportFile(ev) {
  const file = ev.target.files?.[0]
  ev.target.value = ''
  if (!file) return
  try {
    const text = await file.text()
    emit('dismiss-proposal')
    commit(loadInvestigation(text))
  } catch {
    /* ignore malformed file */
  }
}

// --- step navigation / keyboard -----------------------------------------
function goToStep(next) {
  if (next === view.step) { stepSelectorOpen.value = false; return }
  if (view.step === 'conclusion') commitConclusionDraft()
  view.step = next
  stepSelectorOpen.value = false
  nextTick(() => { stepHeadingRef.value?.focus?.() })
}
function goPrevStep() {
  if (stepIndex.value > 0) goToStep(STEP_ORDER[stepIndex.value - 1])
}
function goNextStep() {
  if (stepIndex.value < STEP_ORDER.length - 1) goToStep(STEP_ORDER[stepIndex.value + 1])
}
function onEscape() {
  if (stepSelectorOpen.value) { stepSelectorOpen.value = false; return }
  if (moreMenuOpen.value) { moreMenuOpen.value = false; return }
  if (addEvidenceMenuOpen.value) { addEvidenceMenuOpen.value = false; return }
  if (linkPickerFor.value) { linkPickerFor.value = ''; return }
  if (historyOpen.value) { historyOpen.value = false; return }
  if (restoreConfirmFor.value) { restoreConfirmFor.value = ''; return }
  emit('close')
}

function handleMqChange(e) { isCompactStepNav.value = e.matches }

// --- moveable window --------------------------------------------------
function onHeaderMouseDown(e) {
  if (e.button !== 0) return
  // Don't hijack clicks meant for the header's own controls (More, Close,
  // the status pill's native tooltip, etc.) — only empty header space drags.
  if (e.target.closest('button, input, select, textarea, a')) return
  const el = shellRef.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  // First drag: adopt the current on-screen position as the fixed origin
  // (was centered via the overlay's flex layout until now) so there is no
  // jump when position switches from flex-centered to fixed.
  if (!shellPos.value) shellPos.value = { left: rect.left, top: rect.top }
  dragging.value = true
  dragState = {
    startX: e.clientX, startY: e.clientY,
    baseLeft: shellPos.value.left, baseTop: shellPos.value.top,
    width: rect.width, height: rect.height,
    moved: false,
  }
  window.addEventListener('mousemove', onHeaderMouseMove)
  window.addEventListener('mouseup', onHeaderMouseUp)
  e.preventDefault()
}
function onHeaderMouseMove(e) {
  if (!dragState) return
  const dx = e.clientX - dragState.startX
  const dy = e.clientY - dragState.startY
  if (Math.abs(dx) > 3 || Math.abs(dy) > 3) dragState.moved = true
  // Clamp so at least ~120px of the header stays reachable on every edge —
  // never let the window be dragged fully off-screen with no way back.
  const minVisible = 120
  const maxLeft = Math.max(0, window.innerWidth - minVisible)
  const maxTop = Math.max(0, window.innerHeight - minVisible)
  const minLeft = minVisible - dragState.width
  shellPos.value = {
    left: Math.min(Math.max(dragState.baseLeft + dx, minLeft), maxLeft),
    top: Math.min(Math.max(dragState.baseTop + dy, 0), maxTop),
  }
}
function suppressTrailingClick(e) {
  e.preventDefault()
  e.stopPropagation()
}
function onHeaderMouseUp() {
  const moved = dragState?.moved
  dragState = null
  dragging.value = false
  window.removeEventListener('mousemove', onHeaderMouseMove)
  window.removeEventListener('mouseup', onHeaderMouseUp)
  if (moved) {
    // A real mouseup after a drag always fires a trailing `click` at the
    // release point — if that point happens to be the overlay backdrop
    // (not the shell we just moved there), @click.self would close the
    // dialog out from under the user mid-drag. Swallow that one click.
    window.addEventListener('click', suppressTrailingClick, { capture: true, once: true })
  }
}

onMounted(() => {
  mq = window.matchMedia('(max-width: 720px)')
  isCompactStepNav.value = mq.matches
  if (mq.addEventListener) mq.addEventListener('change', handleMqChange)
  else mq.addListener(handleMqChange)

  view.step = investigationHasContent.value ? 'evidence' : 'question'
  questionEditing.value = !investigationHasContent.value
  // A fresh investigation's title is just the auto-seeded tab name
  // (ensureInvestigation() in App.vue) — never treat it as a real question.
  view.draftQuestion = investigationHasContent.value ? (inv.value.title || '') : ''
  view.draftConclusion = inv.value.conclusion || ''
})
onBeforeUnmount(() => {
  if (mq) {
    if (mq.removeEventListener) mq.removeEventListener('change', handleMqChange)
    else mq.removeListener(handleMqChange)
  }
  // In case the dialog is closed mid-drag (e.g. Escape while dragging).
  window.removeEventListener('mousemove', onHeaderMouseMove)
  window.removeEventListener('mouseup', onHeaderMouseUp)
  window.removeEventListener('click', suppressTrailingClick, { capture: true })
})
</script>

<style scoped>
.dialog-overlay {
  position: fixed;
  inset: 0;
  background: color-mix(in srgb, #000 52%, transparent);
  backdrop-filter: blur(5px) saturate(1.1);
  -webkit-backdrop-filter: blur(5px) saturate(1.1);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
}
.nb-shell {
  background: var(--panel-bg);
  border: 1px solid var(--app-border-soft, var(--border));
  border-radius: 16px;
  width: min(1120px, calc(100vw - 40px));
  height: min(90vh, 900px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 40px 90px -20px rgba(0, 0, 0, 0.55);
}
.nb-shell.dragging { user-select: none; }

/* Header — empty space is a drag handle; user-select:none only while
   actually dragging (see .nb-shell.dragging) so header text stays
   selectable otherwise. */
.nb-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: move;
  gap: 12px;
  min-height: 64px;
  padding: 12px 18px;
  border-bottom: 1px solid var(--app-border-soft, var(--border));
  background: color-mix(in srgb, var(--panel-bg) 55%, var(--bg));
  /* No flex-wrap here: header-right (More/minimize/close) must always stay
     on the title's row, pinned to the right. A long question title already
     wraps within its own box (.nb-header-title has white-space: normal +
     header-left has min-width: 0 to allow shrinking) — letting the HEADER
     itself wrap instead put header-right on its own line, where
     justify-content: space-between collapses a lone wrapped item to the
     LEFT edge. .nb-menu (anchored right:0 to that misplaced .nb-more) then
     opened with most of its width off-screen to the left — invisible and
     unclickable. */
}
.nb-header-left { display: flex; flex-direction: column; gap: 3px; min-width: 0; flex: 1 1 auto; }
.nb-header-label {
  font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase;
  color: var(--fg-dim); font-weight: 700;
}
.nb-header-title-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.nb-header-title { font-size: 17px; font-weight: 700; color: var(--fg); white-space: normal; }
.nb-status-pill {
  display: inline-flex; align-items: center; gap: 6px; font-size: 12px;
  color: var(--fg-dim); padding: 3px 10px; border: 1px solid var(--border);
  border-radius: 999px; flex: none;
}
.nb-status-dot { width: 7px; height: 7px; border-radius: 50%; background: #7f8c8d; }
.nb-status-dot.s-needs_evidence { background: var(--semantic-warning, #e67e22); }
.nb-status-dot.s-ready_to_conclude { background: #2e86de; }
.nb-status-dot.s-closed { background: #27ae60; }
.nb-header-right { display: flex; align-items: center; gap: 6px; flex: none; }
.nb-icon-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 30px; height: 30px; border-radius: 7px; border: 1px solid transparent;
  background: transparent; color: var(--fg-dim); cursor: pointer;
}
.nb-icon-btn:hover:not(:disabled) { background: var(--tb-btn-hover, var(--bg)); color: var(--fg); }
.nb-icon-btn:disabled { opacity: 0.4; cursor: default; }
.nb-more { position: relative; }
.nb-menu {
  position: absolute; top: calc(100% + 6px); right: 0; min-width: 220px;
  display: flex; flex-direction: column; background: var(--panel-bg);
  border: 1px solid var(--border); border-radius: 9px;
  box-shadow: 0 12px 32px -8px rgba(0, 0, 0, 0.4); overflow: hidden; z-index: 6;
}
.nb-menu-item {
  text-align: left; padding: 7px 11px; border: none; background: none;
  color: var(--fg); font-size: 12.5px; cursor: pointer;
}
.nb-menu-item:hover:not(:disabled) { background: var(--tb-btn-hover, var(--bg)); }
.nb-menu-item:disabled { opacity: 0.4; cursor: default; }
.nb-menu-item.danger { color: var(--semantic-error, #e07070); }
.nb-history {
  flex-basis: 100%; display: flex; align-items: center; gap: 6px;
  margin-top: 4px; font-size: 11px; color: var(--fg-dim);
}
.nb-history-label { font-weight: 600; }
.nb-history-dot {
  min-width: 22px; border: 1px solid var(--border); border-radius: 6px;
  background: var(--panel-bg); color: var(--fg-dim); font-size: 11px;
  cursor: pointer; padding: 1px 4px;
}
.nb-history-dot.current { border-color: var(--accent); color: var(--fg); font-weight: 700; }

/* Step nav */
.nb-step-nav {
  display: flex; min-height: 52px; border-bottom: 1px solid var(--app-border-soft, var(--border));
  background: color-mix(in srgb, var(--panel-bg) 55%, var(--bg)); flex: none;
}
.nb-step-tab {
  flex: 1; display: flex; align-items: center; justify-content: center; gap: 8px;
  font-size: 13px; font-weight: 600; color: var(--fg-dim); border: none;
  border-bottom: 2px solid transparent; background: none; cursor: pointer; padding: 0 8px;
}
.nb-step-num {
  width: 20px; height: 20px; border-radius: 50%; border: 1.5px solid currentColor;
  display: inline-flex; align-items: center; justify-content: center; font-size: 11px; flex: none;
}
.nb-step-tab.active { color: var(--accent); border-bottom-color: var(--accent); }
.nb-step-tab.active .nb-step-num { background: var(--accent); border-color: var(--accent); color: #fff; }
.nb-step-nav-compact {
  position: relative; min-height: 52px; display: flex; align-items: center; padding: 0 18px;
  border-bottom: 1px solid var(--app-border-soft, var(--border));
  background: color-mix(in srgb, var(--panel-bg) 55%, var(--bg)); flex: none;
}
.nb-step-compact-btn {
  display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--border);
  border-radius: 8px; background: var(--panel-bg); color: var(--fg); font-size: 13px;
  font-weight: 600; padding: 6px 12px; cursor: pointer;
}
.nb-step-compact-list {
  position: absolute; top: calc(100% + 4px); left: 18px; list-style: none; margin: 0; padding: 4px;
  background: var(--panel-bg); border: 1px solid var(--border); border-radius: 9px;
  box-shadow: 0 12px 32px -8px rgba(0, 0, 0, 0.4); z-index: 6; min-width: 220px;
}
.nb-step-compact-list button {
  width: 100%; text-align: left; padding: 7px 10px; border: none; background: none;
  color: var(--fg); font-size: 12.5px; cursor: pointer; border-radius: 6px;
}
.nb-step-compact-list button:hover { background: var(--tb-btn-hover, var(--bg)); }
.nb-step-compact-list button[aria-selected="true"] { color: var(--accent); font-weight: 700; }

/* Context strip */
.nb-context-strip {
  display: flex; align-items: center; flex-wrap: wrap; gap: 8px; min-height: 40px;
  padding: 8px 18px; border-bottom: 1px solid var(--app-border-soft, var(--border));
  background: var(--bg); flex: none;
}
.nb-chip {
  display: inline-flex; align-items: center; gap: 5px; font-size: 11.5px; color: var(--fg-dim);
  padding: 2px 9px; border: 1px solid var(--border); border-radius: 999px;
  background: var(--panel-bg); white-space: nowrap;
}
.nb-chip.warn {
  color: var(--semantic-warning, #e67e22);
  border-color: color-mix(in srgb, var(--semantic-warning, #e67e22) 45%, var(--border));
}
.nb-context-spacer { flex: 1; }
.nb-link-btn { font-size: 12px; color: var(--accent); background: none; border: none; cursor: pointer; padding: 0; font-weight: 600; }
.nb-context-details {
  padding: 10px 18px; border-bottom: 1px solid var(--app-border-soft, var(--border));
  background: var(--bg); flex: none;
}
.nb-context-details-note { font-size: 11.5px; color: var(--fg-dim); margin: 0 0 6px; }
.nb-digest {
  max-height: 200px; overflow-y: auto; margin: 0; padding: 8px 10px; font-size: 11.5px;
  white-space: pre-wrap; background: var(--panel-bg); border: 1px solid var(--border); border-radius: 7px;
}

/* Working area */
.nb-working {
  flex: 1; min-height: 0; overflow-y: auto; display: grid;
  grid-template-columns: minmax(0, 1fr) 360px; gap: 24px; padding: 20px 18px;
}
@media (max-width: 1000px) {
  .nb-working { grid-template-columns: 1fr; }
}
.nb-main-col { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
.nb-side-col { display: flex; flex-direction: column; gap: 12px; }
.nb-side-col-disabled { font-size: 12px; color: var(--fg-dim); padding: 12px; }
.nb-main-head-row { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.nb-head-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.nb-section-title { font-size: 19px; font-weight: 700; margin: 0; }
.nb-section-helper { font-size: 13px; color: var(--fg-dim); margin: 2px 0 0; }
.nb-sec-hint { font-size: 11.5px; color: var(--fg-dim); margin: 0; line-height: 1.5; }
.nb-sec-hint.warn { color: var(--semantic-warning, #e67e22); }
.nb-meta-empty { font-size: 12px; color: var(--fg-dim); font-style: italic; margin: 0; }

.nb-card {
  background: color-mix(in srgb, var(--panel-bg) 40%, var(--bg));
  border: 1px solid var(--app-border-soft, var(--border)); border-radius: 9px; padding: 12px 14px;
}
.nb-card-title {
  font-size: 11px; font-weight: 700; color: var(--fg-dim); text-transform: uppercase;
  letter-spacing: 0.04em; margin: 0 0 8px;
}
.nb-card-actions { display: flex; gap: 8px; margin-top: 10px; }

.nb-btn {
  display: inline-flex; align-items: center; gap: 6px; padding: 6px 13px; border: 1px solid var(--border);
  border-radius: 8px; background: var(--panel-bg); color: var(--fg); font-size: 12.5px;
  font-weight: 600; cursor: pointer;
}
.nb-btn:hover:not(:disabled) { background: var(--tb-btn-hover, var(--bg)); }
.nb-btn:disabled { opacity: 0.45; cursor: default; }
.nb-btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.nb-btn.primary:disabled { opacity: 0.5; }
.nb-btn.small { padding: 4px 10px; font-size: 11.5px; }

.nb-input {
  padding: 6px 9px; border: 1px solid var(--border); border-radius: 7px; background: var(--bg);
  color: var(--fg); font-size: 13px; font-family: inherit;
}
.nb-input:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 22%, transparent); }
.nb-note { resize: vertical; font-family: inherit; width: 100%; }
.nb-type { flex: none; min-width: 140px; }
.nb-chk { font-size: 11.5px; color: var(--fg-dim); display: flex; align-items: center; gap: 5px; }
.nb-ref-sel { flex: none; max-width: 240px; }

/* Question */
.nb-question-input {
  width: 100%; min-height: 84px; resize: vertical; background: var(--bg); border: 1px solid var(--border);
  border-radius: 9px; padding: 10px 12px; color: var(--fg); font-family: inherit; font-size: 14.5px; line-height: 1.5;
}
.nb-question-display { display: flex; flex-direction: column; gap: 8px; }
.nb-question-text { font-size: 14.5px; font-weight: 600; margin: 0; }
.nb-scope-row { display: flex; flex-wrap: wrap; gap: 6px 20px; font-size: 12.5px; }
.nb-scope-item { display: flex; flex-direction: column; gap: 2px; }
.nb-scope-item .k { color: var(--fg-dim); font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.03em; }
.nb-finding-row { display: flex; align-items: flex-start; gap: 8px; padding: 6px 0; border-top: 1px solid var(--border); cursor: pointer; }
.nb-finding-row:first-of-type { border-top: none; }
.nb-finding-body { display: flex; flex-direction: column; gap: 1px; }
.nb-finding-title { font-size: 12.5px; font-weight: 600; }
.nb-finding-meta { font-size: 11px; color: var(--fg-dim); }

.nb-next-card {
  border: 1px solid var(--accent); background: color-mix(in srgb, var(--accent) 8%, var(--panel-bg));
  border-radius: 9px; padding: 12px 14px; display: flex; align-items: center; justify-content: space-between;
  gap: 16px; flex-wrap: wrap;
}
.nb-next-title { font-weight: 700; font-size: 13.5px; }
.nb-next-reason { font-size: 11.5px; color: var(--fg-dim); margin-top: 3px; line-height: 1.5; }
.nb-next-reason strong { color: var(--fg); font-weight: 600; }
.nb-next-reason-alt {
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px solid color-mix(in srgb, var(--accent) 22%, transparent);
}

/* Evidence */
.nb-add {
  border: 1px solid var(--app-border-soft, var(--border)); border-radius: 9px; padding: 10px;
  display: flex; flex-direction: column; gap: 8px; background: color-mix(in srgb, var(--panel-bg) 40%, var(--bg));
}
.nb-add-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.nb-add-row .nb-input:not(.nb-type) { flex: 1; min-width: 120px; }
.nb-add-refs { display: flex; flex-wrap: wrap; gap: 12px; }
.nb-add-evidence-wrap { position: relative; }
.nb-ev-card {
  display: flex; gap: 10px; background: color-mix(in srgb, var(--panel-bg) 40%, var(--bg));
  border: 1px solid var(--app-border-soft, var(--border)); border-radius: 9px; padding: 10px 12px;
}
.nb-ev-card.stale, .nb-ev-card.broken { border-color: color-mix(in srgb, var(--semantic-warning, #e67e22) 55%, var(--border)); }
.nb-ev-check { flex: none; padding-top: 2px; }
.nb-ev-body { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 4px; }
.nb-ev-top { display: flex; align-items: center; gap: 8px; }
.nb-ev-id { font-family: var(--font-mono, monospace); font-size: 10.5px; color: var(--fg-dim); border: 1px solid var(--border); border-radius: 4px; padding: 1px 5px; flex: none; }
.nb-ev-title-input {
  flex: 1; min-width: 0; font-size: 13.5px; font-weight: 700; border: 1px solid transparent;
  background: transparent; color: var(--fg); padding: 2px 4px; border-radius: 5px; font-family: inherit;
}
.nb-ev-title-input:focus { outline: none; border-color: var(--border); background: var(--bg); }
.nb-ev-value { font-size: 12px; color: var(--fg-dim); }
.nb-ev-source { font-size: 11px; color: var(--fg-dim); display: flex; align-items: center; gap: 6px; }
.nb-stale { font-weight: 700; color: var(--semantic-warning, #e67e22); }
.nb-ev-note {
  width: 100%; resize: vertical; font-family: inherit; font-size: 12px; color: var(--fg-dim);
  background: transparent; border: 1px solid transparent; border-radius: 5px; padding: 2px 4px;
}
.nb-ev-note:focus { outline: none; border-color: var(--border); background: var(--bg); color: var(--fg); }
.nb-ev-actions { display: flex; align-items: center; gap: 12px; margin-top: 2px; flex-wrap: wrap; }
.nb-ev-action { font-size: 11.5px; font-weight: 600; color: var(--accent); background: none; border: none; cursor: pointer; padding: 0; display: inline-flex; align-items: center; gap: 4px; }
.nb-ev-action.muted { color: var(--fg-dim); }
.nb-ev-delete:hover { color: var(--semantic-error, #e74c3c); }
.nb-ev-details { margin-top: 6px; padding-top: 8px; border-top: 1px solid var(--border); display: flex; flex-direction: column; gap: 6px; font-size: 11px; }
.nb-ev-details .detail { display: flex; gap: 6px; }
.nb-ev-details .k { color: var(--fg-dim); text-transform: uppercase; letter-spacing: 0.03em; font-size: 10px; min-width: 90px; }

.nb-restore-confirm {
  border: 1px solid color-mix(in srgb, var(--accent) 35%, var(--border)); border-radius: 8px; padding: 8px 10px;
  background: color-mix(in srgb, var(--accent) 6%, var(--panel-bg)); display: flex; flex-direction: column; gap: 6px;
}
.nb-restore-lead { font-size: 11.5px; color: var(--fg); }
.nb-restore-changes { margin: 0; padding-left: 18px; font-size: 11.5px; color: var(--fg-dim); }
.nb-restore-actions { display: flex; gap: 6px; justify-content: flex-end; }
.nb-restore-done { font-size: 11px; color: var(--fg-dim); display: flex; align-items: center; gap: 8px; }
.nb-restore-undo { background: none; border: none; color: var(--accent); font-size: 11px; font-weight: 600; cursor: pointer; padding: 0; }

/* Verify */
.nb-exp-card {
  border: 1px solid var(--app-border-soft, var(--border)); border-radius: 9px; padding: 12px 14px;
  background: color-mix(in srgb, var(--panel-bg) 40%, var(--bg)); display: flex; flex-direction: column; gap: 8px;
}
.nb-exp-top { display: flex; align-items: center; gap: 8px; }
.nb-exp-title-input { flex: 1; min-width: 0; font-size: 13.5px; font-weight: 700; border: 1px solid transparent; background: transparent; color: var(--fg); padding: 2px 4px; border-radius: 5px; font-family: inherit; }
.nb-exp-title-input:focus { outline: none; border-color: var(--border); background: var(--bg); }
.nb-exp-status {
  font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.03em; color: var(--fg-dim);
  border: 1px solid var(--border); border-radius: 999px; padding: 1px 8px; flex: none;
}
.nb-exp-status.h-supported { color: #27ae60; border-color: #27ae60; }
.nb-exp-status.h-contradicted { color: var(--semantic-warning, #e67e22); border-color: var(--semantic-warning, #e67e22); }
.nb-exp-reason { width: 100%; resize: vertical; font-family: inherit; font-size: 12.5px; background: var(--bg); border: 1px solid var(--border); border-radius: 7px; padding: 6px 8px; color: var(--fg); }
.nb-exp-group { border-top: 1px solid var(--border); padding-top: 8px; }
.nb-exp-group-label { font-size: 10.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.03em; color: var(--fg-dim); margin-bottom: 5px; }
.nb-exp-chips { display: flex; gap: 6px; flex-wrap: wrap; }
.nb-ev-chip { font-family: var(--font-mono, monospace); font-size: 10.5px; border: 1px solid var(--border); border-radius: 4px; padding: 1px 6px; color: var(--fg); }
.nb-exp-hint { font-size: 11.5px; color: var(--fg-dim); font-style: italic; }
.nb-exp-actions { display: flex; gap: 8px; }
.nb-check-card { border: 1px solid var(--border); border-radius: 7px; padding: 8px 10px; margin-top: 6px; background: var(--bg); }
.nb-check-row { display: flex; gap: 10px; font-size: 12px; align-items: flex-start; }
.nb-check-row + .nb-check-row { margin-top: 5px; }
.nb-check-row .k { color: var(--fg-dim); flex: none; width: 96px; padding-top: 4px; }
.nb-check-row .v { flex: 1; }
.nb-outcome-pill { font-size: 10px; font-weight: 700; text-transform: uppercase; color: var(--fg-dim); border: 1px solid var(--border); border-radius: 999px; padding: 1px 8px; }
.nb-check-mini { font-size: 12px; color: var(--fg); display: flex; align-items: center; gap: 6px; }
.nb-check-mini + .nb-check-mini { margin-top: 5px; }
.nb-link-picker { border: 1px solid var(--border); border-radius: 8px; padding: 10px; display: flex; flex-direction: column; gap: 8px; background: var(--bg); }
.nb-link-rel-row { display: flex; gap: 12px; }

.nb-chain { font-size: 11.5px; color: var(--fg-dim); line-height: 1.5; padding: 4px 0; }
.nb-conclusion-box {
  width: 100%; min-height: 140px; resize: vertical; background: var(--bg); border: 1px solid var(--border);
  border-radius: 9px; padding: 10px 12px; color: var(--fg); font-family: inherit; font-size: 13.5px; line-height: 1.55;
}
.nb-ai-actions { display: flex; gap: 8px; }
.nb-preview { border: 1px solid var(--border); border-radius: 9px; padding: 12px 14px; background: var(--bg); }
.nb-preview-section { margin-bottom: 10px; font-size: 12px; }
.nb-preview-section ul { margin: 4px 0 0; padding-left: 18px; }

/* AI assistance */
.nb-assist-card { display: flex; flex-direction: column; gap: 8px; }
.nb-assist-heading { display: flex; align-items: center; gap: 8px; font-size: 12.5px; font-weight: 700; }
.nb-assist-body { font-size: 12.5px; color: var(--fg-dim); line-height: 1.5; margin: 0; }
/* Prose AI reply — demo `.chat`: soft accent tint, no hard border, labelled. */
.nb-assist-note {
  border-radius: 8px;
  padding: 11px 12px;
  background: color-mix(in srgb, var(--accent) 9%, var(--panel-bg));
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.nb-assist-note-label {
  font-size: 9.5px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--accent);
}
.nb-assist-note-block { display: flex; flex-direction: column; gap: 4px; }
.nb-assist-note-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--fg);
  margin: 2px 0 0;
}
.nb-assist-note-list {
  margin: 0;
  padding-left: 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.nb-assist-note-list li {
  font-size: 12px;
  color: var(--fg);
  line-height: 1.5;
}
.nb-assist-note { max-height: 320px; overflow-y: auto; }
.nb-suggestion { border: 1px solid var(--border); background: color-mix(in srgb, var(--semantic-warning, #e67e22) 8%, var(--panel-bg)); border-radius: 8px; padding: 10px; display: flex; flex-direction: column; gap: 6px; }
.nb-suggestion-label { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; color: var(--semantic-warning, #e67e22); }
.nb-suggestion-text { font-size: 12.5px; margin: 0; line-height: 1.4; }

/* §10 — inline AI proposal review (right panel) */
.nb-proposal-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  border-color: color-mix(in srgb, var(--semantic-warning, #e67e22) 40%, var(--border));
  background: color-mix(in srgb, var(--semantic-warning, #e67e22) 6%, var(--panel-bg));
}
.nb-proposal-lead { font-size: 11.5px; color: var(--fg-dim); line-height: 1.45; margin: -2px 0 0; }
.nb-proposal-summary { font-size: 12.5px; color: var(--fg); line-height: 1.5; margin: 0; }
.nb-proposal-notes {
  margin: 0;
  padding-left: 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.nb-proposal-notes li { font-size: 12px; color: var(--fg); line-height: 1.5; }
.nb-prop-group { display: flex; flex-direction: column; gap: 6px; }
.nb-prop-group-label { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; color: var(--fg-dim); }
.nb-prop-group.rejected .nb-prop-group-label { color: var(--semantic-warning, #e67e22); }
.nb-prop-op {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 7px 9px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-bg);
  font-size: 12px;
  cursor: pointer;
}
.nb-prop-op.confirm { border-color: color-mix(in srgb, var(--semantic-warning, #e67e22) 55%, var(--border)); }
.nb-prop-op > input[type="checkbox"] { margin-top: 2px; flex: none; accent-color: var(--accent); }
.nb-prop-op-body { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.nb-prop-op-line { line-height: 1.4; }
.nb-prop-sources { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; }
.nb-prop-sources-label { font-size: 9.5px; text-transform: uppercase; letter-spacing: 0.03em; color: var(--fg-dim); }
.nb-prop-src {
  font-size: 10.5px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: color-mix(in srgb, var(--accent) 10%, transparent);
  color: var(--fg);
}
.nb-prop-confirm { font-size: 10.5px; color: var(--semantic-warning, #e67e22); display: flex; align-items: flex-start; gap: 5px; line-height: 1.4; }
.nb-prop-confirm input { margin-top: 1px; flex: none; accent-color: var(--accent); }
.nb-prop-note { font-size: 10.5px; color: var(--fg-dim); line-height: 1.4; }
.nb-prop-rejected { font-size: 11px; color: var(--fg-dim); line-height: 1.4; }
.nb-prop-model { font-size: 10px; color: var(--fg-dim); line-height: 1.45; margin: 0; }
.nb-prop-actions { display: flex; align-items: center; gap: 6px; padding-top: 2px; }
.nb-prop-spacer { flex: 1; }

/* Footer */
.nb-footer {
  display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 10px 18px;
  border-top: 1px solid var(--app-border-soft, var(--border)); background: color-mix(in srgb, var(--panel-bg) 55%, var(--bg)); flex: none;
}
.nb-save-state { font-size: 11px; color: var(--fg-dim); }
.nb-footer-actions { display: flex; align-items: center; gap: 6px; }
.nb-footer-sep { width: 1px; height: 18px; background: var(--border); margin: 0 4px; }
</style>
