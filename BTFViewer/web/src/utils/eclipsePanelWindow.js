// SWT routes this popup into a Browser hosted in an Eclipse view. Teleporting
// the existing panel keeps its Vue state, workers and trace in the editor.
export function createEclipsePanelWindow(panel, dark) {
  const popup = window.open('', '_blank', 'popup')
  if (!popup) throw new Error('Eclipse did not create a panel browser')

  try {
    const doc = popup.document
    doc.title = panel === 'cpu' ? 'BTF CPU Load' : 'BTF Analysis'
    doc.documentElement.lang = document.documentElement.lang
    const base = doc.createElement('base')
    base.href = document.baseURI
    doc.head.append(base)
    for (const stylesheet of document.head.querySelectorAll('style, link[rel="stylesheet"]')) {
      doc.head.append(doc.importNode(stylesheet, true))
    }

    const target = doc.createElement('div')
    target.className = 'app eclipse-panel-window'
    target.classList.toggle('dark', dark)
    doc.body.append(target)
    return { target }
  } catch (error) {
    popup.close()
    throw error
  }
}
