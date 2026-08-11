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
      className="report-header-block bg-white border border-slate-200 rounded-2xl mb-4 overflow-hidden shadow-sm"
      id="report-header"
    >
      <div className="bg-gradient-to-r from-[#1e3a5f] to-[#2a5298] px-6 py-4">
        <div className="flex items-center justify-center gap-4">
          {/* Logo */}
          <div className="flex-shrink-0">
            <img
              src="/college-logo.png"
              alt="College Logo"
              className="w-16 h-16 object-contain rounded-full bg-white p-1"
              onError={(e) => {
                e.target.style.display = 'none';
              }}
            />
          </div>

          {/* Text block */}
          <div className="text-center text-white">
            <p className="text-[11px] font-semibold text-blue-200 tracking-widest uppercase mb-0.5">
              ವಿಶ್ವೇಶ್ವರಯ್ಯ ತಾಂತ್ರಿಕ ವಿಶ್ವವಿದ್ಯಾಲಯ
            </p>
            <h1 className="text-base font-extrabold leading-tight tracking-wide">
              VISVESVARAYA TECHNOLOGICAL UNIVERSITY, BELAGAVI-590018
            </h1>
            <h2 className="text-sm font-bold leading-tight mt-1">
              GOVERNMENT ENGINEERING COLLEGE MOSALEHOSAHALLI, HASSAN
            </h2>
            <div className="mt-1.5 inline-block bg-white/15 rounded-full px-4 py-0.5">
              <p className="text-xs font-semibold tracking-wider">
                DEPARTMENT OF COMPUTER SCIENCE AND ENGINEERING
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Thin accent bar */}
      <div className="h-1 bg-gradient-to-r from-amber-400 via-orange-400 to-amber-400" />
    </div>
  );
}

/**
 * PrintReportHeader — used only inside the printable section (no class gating).
 */
export function PrintReportHeader() {
  return (
    <div
      style={{
        textAlign: 'center',
        borderBottom: '2px solid #1e3a5f',
        paddingBottom: '12px',
        marginBottom: '16px',
      }}
    >
      <img
        src="/college-logo.png"
        alt="Logo"
        style={{ width: 64, height: 64, objectFit: 'contain', marginBottom: 6 }}
        onError={(e) => { e.target.style.display = 'none'; }}
      />
      <p style={{ fontSize: 13, fontWeight: 800, margin: '2px 0', color: '#1e3a5f' }}>
        VISVESVARAYA TECHNOLOGICAL UNIVERSITY, BELAGAVI-590018
      </p>
      <p style={{ fontSize: 12, fontWeight: 700, margin: '2px 0', color: '#1e3a5f' }}>
        GOVERNMENT ENGINEERING COLLEGE MOSALEHOSAHALLI, HASSAN
      </p>
      <p style={{ fontSize: 11, fontWeight: 600, margin: '2px 0', color: '#2a5298' }}>
        DEPARTMENT OF COMPUTER SCIENCE AND ENGINEERING
      </p>
    </div>
  );
}
