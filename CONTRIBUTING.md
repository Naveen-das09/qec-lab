# Contributing to QEC Lab

Start with the local setup in README.md and run the test suite before submitting changes.

For a scientific change, state the exact circuit, noise assumptions, observable, decoder assumptions, sampling rule, and statistical interpretation. Add a test against a known limiting case or independently replayed sample. Do not add fabricated benchmark numbers to the interface.

For an agent change, test valid and invalid tool calls, bounded execution, provider failures, and evidence grounding. Mocked protocol tests do not establish live model quality; distinguish the two in your change description. Never commit keys or private conversations.

For interface work, keep keyboard navigation, semantic controls, reduced motion, empty/error states, and narrow screens working. The experiment API is the source of truth for saved product data. Browser storage is reserved for device preferences.

Keep changes focused. Describe the problem, final behavior, scientific limitations, and validation. Contributions use the project MIT license; cite and retain notices for any third-party material.
