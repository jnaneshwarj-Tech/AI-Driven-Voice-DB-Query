/**
 * ReportHeader.jsx
 * Institutional header for dashboard and print views.
 * VISVESVARAYA TECHNOLOGICAL UNIVERSITY, BELAGAVI-590018
 * GOVERNMENT ENGINEERING COLLEGE MOSALEHOSAHALLI, HASSAN
 * DEPARTMENT OF COMPUTER SCIENCE AND ENGINEERING
 */

export default function ReportHeader({ showInDashboard = false }) {
  if (!showInDashboard) return null;

  return (
    <div
      className="report-header-block card overflow-hidden mb-4"
      id="report-header"
    >
      <div className="bg-gradient-to-r from-brand-deep to-brand px-6 py-4">
        <div className="flex items-center justify-center gap-4">
          {/* Logo — the genuine VTU emblem is 738×411 (landscape). The plate
              follows that ratio so the emblem keeps its own proportions; a
              square or circular box would shrink it or crop the corners. */}
          <div className="flex-shrink-0">
            <img
              src="/college-logo.png"
              alt="Visvesvaraya Technological University"
              className="h-14 w-[100px] object-contain rounded-lg bg-white px-1.5 py-1 shadow-sm"
              onError={(e) => {
                e.target.style.display = 'none';
              }}
            />
          </div>

          {/* Text block — institutional names stay as written (official
              English + Kannada headings; they are not UI chrome). */}
          <div className="text-center text-white">
            <p className="text-[11px] font-semibold text-white/75 tracking-widest uppercase mb-0.5 font-kannada">
              ವಿಶ್ವೇಶ್ವರಯ್ಯ ತಾಂತ್ರಿಕ ವಿಶ್ವವಿದ್ಯಾಲಯ
            </p>
            <h1 className="text-base font-extrabold leading-tight tracking-wide text-white">
              VISVESVARAYA TECHNOLOGICAL UNIVERSITY, BELAGAVI-590018
            </h1>
            <h2 className="text-sm font-bold leading-tight mt-1 text-white">
              GOVERNMENT ENGINEERING COLLEGE MOSALEHOSAHALLI, HASSAN
            </h2>
            <div className="mt-1.5 inline-block bg-white/15 rounded-full px-4 py-0.5">
              <p className="text-xs font-semibold tracking-wider text-white">
                DEPARTMENT OF COMPUTER SCIENCE AND ENGINEERING
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Thin accent bar — gold token so it follows the theme on screen */}
      <div className="h-1 bg-gradient-to-r from-accent-strong via-accent to-accent-strong" />
    </div>
  );
}

/**
 * PrintReportHeader — used only inside the printable section (no class gating).
 * Colours below are deliberately fixed ink-on-white (#35685B / #437A6C):
 * printed output must not follow the screen theme or the dark-mode tokens.
 * The logo is /college-logo.png (the genuine VTU emblem, 738×411) and is
 * printed at that same ratio; onError stays so a missing asset cannot leave a
 * broken-image glyph on a report that is about to be handed to an office.
 */
export function PrintReportHeader() {
  return (
    <div
      style={{
        textAlign: 'center',
        borderBottom: '2px solid #35685B',
        paddingBottom: '12px',
        marginBottom: '16px',
      }}
    >
      <img
        src="/college-logo.png"
        alt="Logo"
        style={{ width: 88, height: 49, objectFit: 'contain', marginBottom: 6 }}
        onError={(e) => { e.target.style.display = 'none'; }}
      />
      <p style={{ fontSize: 13, fontWeight: 800, margin: '2px 0', color: '#35685B' }}>
        VISVESVARAYA TECHNOLOGICAL UNIVERSITY, BELAGAVI-590018
      </p>
      <p style={{ fontSize: 12, fontWeight: 700, margin: '2px 0', color: '#35685B' }}>
        GOVERNMENT ENGINEERING COLLEGE MOSALEHOSAHALLI, HASSAN
      </p>
      <p style={{ fontSize: 11, fontWeight: 600, margin: '2px 0', color: '#437A6C' }}>
        DEPARTMENT OF COMPUTER SCIENCE AND ENGINEERING
      </p>
    </div>
  );
}
