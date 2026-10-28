/**
 * PrintReport.jsx — Compact Professional Academic Report (No Photos)
 *
 * Layout:
 *   [University Header + Logo]
 *   [Personal Information table — 2-column grid, compact]
 *   [Academic Performance table — Sem | SGPA | CGPA]
 *   [Signature Section — BLANK lines for handwritten signing]
 *
 * Print rules:
 *   - Compact spacing, no unnecessary gaps
 *   - page-break-inside: avoid on sections
 *   - repeat table headers on page break
 *   - Signature stays at bottom of last page
 *
 * COLOUR POLICY: every inline colour in this file is a deliberate fixed
 * ink-on-white value (forest green #35685B, greys, #F1F4F1 banding). It must
 * NOT be swapped for theme tokens: this component renders into the hidden print
 * area and goes to paper via the browser print dialog, where the document
 * must always read as black-ink-on-white regardless of the screen theme.
 *
 * LANGUAGE POLICY: the chrome labels live in i18n/sections/print.*.js so the
 * report follows the interface language. The university, college and
 * department names are the institution's registered English names and stay
 * untranslated, and USN/SGPA/CGPA are identifiers and acronyms, not prose.
 */
import { useI18n } from '../context/LanguageContext';

const UNIVERSITY = 'VISVESVARAYA TECHNOLOGICAL UNIVERSITY, BELAGAVI-590018';
const COLLEGE    = 'GOVERNMENT ENGINEERING COLLEGE MOSALEHOSAHALLI, HASSAN';
const DEPT       = 'DEPARTMENT OF COMPUTER SCIENCE AND ENGINEERING';

function nowStr(locale) {
  return new Date().toLocaleString(locale, {
    day: '2-digit', month: 'long', year: 'numeric',
    hour: '2-digit', minute: '2-digit', hour12: true,
  });
}

function computeCgpa(rows) {
  const groups = {};
  for (const r of rows) {
    const key = r.usn || r.name || '';
    if (!groups[key]) groups[key] = [];
    groups[key].push({ sem: r.semester ?? 0, sgpa: parseFloat(r.sgpa) || 0 });
  }
  const cgpaMap = {};
  for (const [key, sems] of Object.entries(groups)) {
    sems.sort((a, b) => a.sem - b.sem);
    let sum = 0;
    cgpaMap[key] = {};
    sems.forEach((s, i) => {
      sum += s.sgpa;
      cgpaMap[key][s.sem] = (sum / (i + 1)).toFixed(2);
    });
  }
  return cgpaMap;
}

// Ordered personal field definitions — labels come from print.f.<field>,
// which is why the field names here must stay identical to the DB columns.
const PERSONAL_FIELDS = [
  'usn', 'name', 'dob', 'gender', 'blood_group', 'father_name', 'mother_name',
  'phone', 'email', 'address', 'permanent_address', 'current_address',
  'religion', 'caste', 'category', 'aadhar_no', 'year_and_branch', 'year_of_joining',
];

// Inject compact print CSS once
const PRINT_STYLE = `
  @media print {
    * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
    body { margin: 0; padding: 0; }
    #print-report-area { padding: 12px 16px !important; }
    .print-section { page-break-inside: avoid; break-inside: avoid; }
    .print-table { page-break-inside: auto; }
    .print-table tr { page-break-inside: avoid; break-inside: avoid; }
    .print-table thead { display: table-header-group; }
    .print-sig { page-break-inside: avoid; break-inside: avoid; }
    @page { margin: 12mm 14mm; size: A4 portrait; }
  }
`;

export default function PrintReport({ data, username, role, query }) {
  const { t, isKn } = useI18n();
  if (!data?.length) return null;

  const hasGpa      = data.some(r => r.sgpa != null || r.cgpa != null);
  const hasPersonal = data.some(r =>
    r.father_name || r.mother_name || r.dob || r.blood_group || r.address || r.phone
  );

  const uniqueUsns      = [...new Set(data.map(r => r.usn).filter(Boolean))];
  const isSingleStudent = uniqueUsns.length === 1;
  const profileRow      = isSingleStudent ? data[0] : null;

  const academicRows = hasGpa
    ? data.filter(r => r.sgpa != null || r.semester != null)
    : [];
  const cgpaMap = hasGpa ? computeCgpa(academicRows.length ? academicRows : data) : {};

  const flatHeaders = [
    ...new Set(data.flatMap(r => Object.keys(r)))
  ].filter(h => !['photo_url', 'image_url', 'photo'].includes(h));

  // Personal fields that have a value
  const personalFields = PERSONAL_FIELDS.filter((field) => profileRow?.[field]);

  return (
    <div
      id="print-report-area"
      style={{
        fontFamily: isKn
          ? "'Nirmala UI', 'Noto Sans Kannada', 'Tunga', Arial, sans-serif"
          : 'Arial, sans-serif',
        color: '#111',
        background: '#fff', padding: '16px 20px',
        fontSize: 10, lineHeight: isKn ? 1.7 : 1.4,
      }}
    >
      {/* Inject print CSS */}
      <style dangerouslySetInnerHTML={{ __html: PRINT_STYLE }} />

      {/* ── Institutional Header ───────────────────────────────────────────── */}
      <div
        className="print-section"
        style={{
          textAlign: 'center', borderBottom: '2px solid #24344B',
          paddingBottom: 8, marginBottom: 10,
        }}
      >
        <img
          src="/college-logo.png"
          alt=""
          style={{ width: 74, height: 41, objectFit: 'contain', marginBottom: 4 }}
          /* Genuine VTU emblem (738×411) printed at its own ratio. onError stays
             so a missing asset never leaves a broken-image glyph on paper. */
          onError={e => { e.target.style.display = 'none'; }}
        />
        <p style={{ fontSize: 13, fontWeight: 800, margin: '2px 0', color: '#24344B' }}>
          {UNIVERSITY}
        </p>
        <p style={{ fontSize: 11, fontWeight: 700, margin: '2px 0', color: '#24344B' }}>
          {COLLEGE}
        </p>
        <p style={{ fontSize: 10, fontWeight: 600, margin: '2px 0', color: '#304460' }}>
          {DEPT}
        </p>
        <p style={{
          fontSize: 11, fontWeight: 700, margin: '6px 0 0',
          color: '#24344B', textDecoration: 'underline',
        }}>
          {t('print.title')}
        </p>
        {query && (
          <p style={{ fontSize: 9, color: '#66645F', margin: '4px 0 0', fontStyle: 'italic' }}>
            {query}
          </p>
        )}
      </div>

      {/* ══════════════════════════════════════════════════
          SINGLE STUDENT VIEW
          ═════════════════════════════════════════════════ */}
      {isSingleStudent && (
        <>
          {/* ── Personal Info — 2-column compact grid ── */}
          {hasPersonal && profileRow && personalFields.length > 0 && (
            <div
              className="print-section"
              style={{
                marginBottom: 10, padding: '8px 10px',
                background: '#F3E8D0', border: '1px solid #E2D7C6',
                borderRadius: 4,
              }}
            >
              <p style={{
                fontSize: 10, fontWeight: 700, color: '#24344B',
                margin: '0 0 6px', textTransform: 'uppercase', letterSpacing: 0.4,
              }}>
                {t('print.personal')}
              </p>
              {/* Two-column grid */}
              <div style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: '2px 16px',
              }}>
                {personalFields.map((field) => (
                  <div key={field} style={{ display: 'flex', gap: 4 }}>
                    <span style={{ fontWeight: 700, color: '#292B30', minWidth: 100, fontSize: 9 }}>
                      {t(`print.f.${field}`)}:
                    </span>
                    <span style={{ color: '#414348', fontSize: 9, wordBreak: 'break-word' }}>
                      {String(profileRow[field])}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── Academic Performance Table ── */}
          {hasGpa && academicRows.length > 0 && (
            <div className="print-section" style={{ marginBottom: 10 }}>
              <p style={{
                fontSize: 10, fontWeight: 700, color: '#24344B',
                margin: '0 0 4px', textTransform: 'uppercase', letterSpacing: 0.4,
              }}>
                {t('print.academic')}
              </p>
              <table
                className="print-table"
                style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}
              >
                <thead>
                  <tr style={{ background: '#24344B', color: '#FFFDF7' }}>
                    <th style={{ ...TH, width: '8%' }}>#</th>
                    <th style={{ ...TH, width: '32%' }}>{t('print.semester')}</th>
                    <th style={{ ...TH, width: '30%' }}>{t('print.sgpa')}</th>
                    <th style={{ ...TH, width: '30%' }}>{t('print.cgpaCumulative')}</th>
                  </tr>
                </thead>
                <tbody>
                  {academicRows.map((row, i) => {
                    const key   = row.usn || row.name || '';
                    const sem   = row.semester ?? 0;
                    const cgpaV = row.cgpa != null
                      ? parseFloat(row.cgpa).toFixed(2)
                      : cgpaMap[key]?.[sem] ?? '';
                    return (
                      <tr key={i} style={{ background: i % 2 === 0 ? '#FFFDF7' : '#F8F3EA' }}>
                        <td style={{ ...TD, textAlign: 'center' }}>{i + 1}</td>
                        <td style={{ ...TD, textAlign: 'center', fontWeight: 600 }}>
                          {t('print.semesterN', { n: row.semester ?? '' })}
                        </td>
                        <td style={{ ...TD, textAlign: 'center', fontWeight: 700, color: '#24344B' }}>
                          {row.sgpa != null ? parseFloat(row.sgpa).toFixed(2) : ''}
                        </td>
                        <td style={{ ...TD, textAlign: 'center', fontWeight: 700, color: '#B66A45' }}>
                          {cgpaV}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* ══════════════════════════════════════════════════
          MULTI-STUDENT or GENERIC TABLE
          ═════════════════════════════════════════════════ */}
      {!isSingleStudent && (
        hasGpa ? (
          <div className="print-section" style={{ marginBottom: 10 }}>
            <table
              className="print-table"
              style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}
            >
              <thead>
                <tr style={{ background: '#24344B', color: '#FFFDF7' }}>
                  <th style={{ ...TH, width: '5%' }}>#</th>
                  {data.some(r => r.usn)             && <th style={TH}>{t('print.usn')}</th>}
                  {data.some(r => r.name)            && <th style={TH}>{t('print.name')}</th>}
                  {data.some(r => r.semester != null) && <th style={{ ...TH, width: '8%' }}>{t('print.sem')}</th>}
                  {data.some(r => r.sgpa != null)    && <th style={{ ...TH, width: '12%' }}>{t('print.sgpa')}</th>}
                  <th style={{ ...TH, width: '18%' }}>{t('print.cgpa')}</th>
                </tr>
              </thead>
              <tbody>
                {data.map((row, i) => {
                  const key   = row.usn || row.name || '';
                  const sem   = row.semester ?? 0;
                  const cgpaV = row.cgpa != null
                    ? parseFloat(row.cgpa).toFixed(2)
                    : cgpaMap[key]?.[sem] ?? '';
                  return (
                    <tr key={i} style={{ background: i % 2 === 0 ? '#FFFDF7' : '#F8F3EA' }}>
                      <td style={{ ...TD, textAlign: 'center' }}>{i + 1}</td>
                      {data.some(r => r.usn)             && <td style={{ ...TD, fontFamily: 'monospace', fontSize: 8, whiteSpace: 'nowrap' }}>{row.usn || ''}</td>}
                      {data.some(r => r.name)            && <td style={{ ...TD, fontWeight: 600 }}>{row.name || ''}</td>}
                      {data.some(r => r.semester != null) && <td style={{ ...TD, textAlign: 'center' }}>{row.semester ?? ''}</td>}
                      {data.some(r => r.sgpa != null)    && <td style={{ ...TD, textAlign: 'center', fontWeight: 700, color: '#24344B' }}>{row.sgpa != null ? parseFloat(row.sgpa).toFixed(2) : ''}</td>}
                      <td style={{ ...TD, textAlign: 'center', fontWeight: 700, color: '#B66A45' }}>{cgpaV}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="print-section" style={{ marginBottom: 10 }}>
            <table
              className="print-table"
              style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'auto', fontSize: 9 }}
            >
              <thead>
                <tr style={{ background: '#24344B', color: '#FFFDF7' }}>
                  {flatHeaders.map(h => (
                    <th key={h} style={TH}>{h.replace(/_/g, ' ').toUpperCase()}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.map((row, i) => (
                  <tr key={i} style={{ background: i % 2 === 0 ? '#FFFDF7' : '#F8F3EA' }}>
                    {flatHeaders.map(h => (
                      <td key={h} style={TD}>{row[h] != null ? String(row[h]) : ''}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      {/* ── Signature Section — BLANK for handwritten signing ──────────────── */}
      <div
        className="print-sig"
        style={{ borderTop: '1px solid #E2D7C6', paddingTop: 10, marginTop: 8 }}
      >
        <table style={{ width: '100%' }}>
          <tbody>
            <tr>
              <td style={{ width: '50%', verticalAlign: 'top', paddingRight: 16 }}>
                <p style={{ fontSize: 10, margin: '0 0 2px', fontWeight: 700, color: '#24344B' }}>{t('print.preparedBy')}</p>
                <p style={{ fontSize: 10, margin: '14px 0 3px', color: '#66645F' }}>{t('print.signature')}</p>
                <p style={{ fontSize: 10, margin: '3px 0', fontWeight: 700, color: '#24344B' }}>({role || t('print.staff')})</p>
                {/* Name intentionally blank — for handwritten signing */}
              </td>
              <td style={{ width: '50%', verticalAlign: 'top' }}>
                <p style={{ fontSize: 10, margin: '0 0 3px', fontWeight: 700, color: '#24344B' }}>{t('print.generatedOn')}</p>
                <p style={{ fontSize: 10, margin: 0, color: '#66645F' }}>{nowStr(isKn ? 'kn-IN' : 'en-IN')}</p>
              </td>
            </tr>
          </tbody>
        </table>
        {/* Footnote: fixed print secondary text (#66645F) — legible on paper in any theme */}
        <p style={{ fontSize: 8, color: '#66645F', textAlign: 'center', marginTop: 10 }}>
          {t('print.footnote')} · {COLLEGE}
        </p>
      </div>
    </div>
  );
}

const TH = {
  padding: '5px 7px', fontSize: 9, fontWeight: 700,
  textAlign: 'center', border: '1px solid #304460',
};
const TD = {
  padding: '4px 6px', fontSize: 9,
  border: '1px solid #E2D7C6', textAlign: 'left',
};
