import React from 'react';
import GpaTable from './GpaTable';
import {
  User, Phone, MapPin, Mail, Droplet, Calendar,
  GraduationCap, BookOpen, Shield, AlertCircle, ChevronRight
} from 'lucide-react';

// ── Field category classification ─────────────────────────────────────────────
// These are the "always academic" keys — never shown in personal section
const ACADEMIC_KEYS = new Set([
  'semester', 'sgpa', 'cgpa', 'year',
  // wide-format columns like sem_1_sgpa are handled by regex below
]);

const isAcademicKey = (k) =>
  ACADEMIC_KEYS.has(k.toLowerCase()) ||
  /^sem_\d+_(sgpa|cgpa)$/.test(k.toLowerCase());

// Keys that are always shown in a dedicated section or as identity fields
const IDENTITY_KEYS = new Set(['usn', 'name', 'student_id', 'created_at', 'updated_at']);

// Personal field icons map
const FIELD_ICONS = {
  phone: <Phone className="w-3.5 h-3.5 text-slate-400" />,
  mobile: <Phone className="w-3.5 h-3.5 text-slate-400" />,
  email: <Mail className="w-3.5 h-3.5 text-slate-400" />,
  address: <MapPin className="w-3.5 h-3.5 text-slate-400" />,
  permanent_address: <MapPin className="w-3.5 h-3.5 text-slate-400" />,
  current_address: <MapPin className="w-3.5 h-3.5 text-slate-400" />,
  dob: <Calendar className="w-3.5 h-3.5 text-slate-400" />,
  blood_group: <Droplet className="w-3.5 h-3.5 text-red-400" />,
};

// Graduation status badge
function GradBadge({ status }) {
  if (!status) return null;
  const isGrad = String(status).toUpperCase() === 'GRADUATED';
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold ${
      isGrad
        ? 'bg-green-100 text-green-700 border border-green-200'
        : 'bg-blue-100 text-blue-700 border border-blue-200'
    }`}>
      {isGrad ? <GraduationCap className="w-3 h-3" /> : <BookOpen className="w-3 h-3" />}
      {isGrad ? 'GRADUATED' : 'ACTIVE'}
    </span>
  );
}

// Pretty-print a field label
function prettyLabel(key) {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase());
}

// Format a field value nicely
function prettyValue(key, val) {
  if (val === null || val === undefined || val === '') return '—';
  const s = String(val);
  if (key === 'dob' || key === 'date_of_birth') {
    try {
      return new Date(s).toLocaleDateString('en-IN', { year: 'numeric', month: 'short', day: '2-digit' });
    } catch { return s; }
  }
  if (key === 'blood_group') return s.toUpperCase();
  return s;
}

// Determine section grouping for a personal field
function getFieldGroup(key) {
  const k = key.toLowerCase();
  if (['father_name', 'mother_name', 'guardian_name', 'parent_name', 'religion', 'caste', 'sub_caste', 'category'].includes(k)) return 'family';
  if (['dob', 'gender', 'blood_group', 'aadhar_no', 'status', 'nationality'].includes(k)) return 'identity';
  if (['phone', 'mobile', 'email', 'emergency_contact_number', 'emergency_contact', 'emergency_phone'].includes(k) || k.includes('contact') || k.includes('phone') || k.includes('mobile')) return 'contact';
  if (k.includes('address')) return 'address';
  if (['branch', 'division', 'section', 'domain', 'year_and_branch', 'year_of_joining', 'admission_year', 'current_year', 'current_sem', 'student_type', 'estimated_semester', 'source_file'].includes(k)) return 'academic_meta';
  return 'other';
}

// ── InfoRow component ─────────────────────────────────────────────────────────
function InfoRow({ label, value, icon }) {
  const displayVal = value !== null && value !== undefined && value !== '' ? String(value) : null;
  if (!displayVal) return null;
  return (
    <div className="flex items-start justify-between border-b border-slate-50 pb-1.5 gap-2">
      <span className="text-slate-500 flex items-center gap-1.5 flex-shrink-0 text-xs">
        {icon}
        {label}
      </span>
      <span className="font-medium text-slate-800 text-xs text-right break-words max-w-[60%]">
        {displayVal}
      </span>
    </div>
  );
}

// ── Section component ─────────────────────────────────────────────────────────
function Section({ title, icon, children, empty }) {
  return (
    <div className="space-y-2">
      <h3 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
        {icon}
        {title}
      </h3>
      {empty ? (
        <p className="text-xs text-slate-400 italic flex items-center gap-1">
          <AlertCircle className="w-3 h-3" /> Information not available
        </p>
      ) : (
        <div className="flex flex-col gap-1.5 text-sm">
          {children}
        </div>
      )}
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────
export default function CombinedStudentView({ data, responseLanguage }) {
  if (!data?.length) return null;

  // ── Group rows by USN (or name) ──────────────────────────────────────────
  const students = {};
  for (const row of data) {
    const key = row.usn || row.name || 'Unknown';
    if (!students[key]) {
      // Separate personal and academic fields dynamically
      const personal = {};
      const academicMeta = {};  // branch, section, etc.
      for (const [k, v] of Object.entries(row)) {
        if (IDENTITY_KEYS.has(k.toLowerCase())) continue;
        if (isAcademicKey(k)) continue;
        const group = getFieldGroup(k);
        if (group === 'academic_meta') {
          academicMeta[k] = v;
        } else {
          personal[k] = v;
        }
      }
      students[key] = {
        usn: row.usn,
        name: row.name,
        personal,
        academicMeta,
        graduation: {
          graduation_year: row.graduation_year,
          graduation_status: row.graduation_status,
          student_type: row.student_type,
          admission_batch: row.admission_batch ?? row.admission_year,
          current_year: row.current_year,
          current_sem: row.current_sem ?? row.estimated_semester,
        },
        academic: [],
      };
    }
    // Collect academic rows
    if (row.semester != null || row.sgpa != null || row.cgpa != null) {
      students[key].academic.push(row);
    }
    // Keep graduation data updated (may arrive in later rows)
    if (row.graduation_year && !students[key].graduation.graduation_year) {
      students[key].graduation.graduation_year = row.graduation_year;
      students[key].graduation.graduation_status = row.graduation_status;
    }
  }

  // ── Kannada section labels ───────────────────────────────────────────────
  const isKannada = responseLanguage === 'kannada' || responseLanguage === 'mixed';
  const LABELS = {
    profile: isKannada ? 'ಸಂಪೂರ್ಣ ವಿದ್ಯಾರ್ಥಿ ಪ್ರೊಫೈಲ್' : 'Complete Student Profile',
    personal: isKannada ? 'ವೈಯಕ್ತಿಕ ಮಾಹಿತಿ' : 'Personal Information',
    academic: isKannada ? 'ಶೈಕ್ಷಣಿಕ ಮಾಹಿತಿ' : 'Academic Information',
    graduation: isKannada ? 'ಪದವಿ ಮಾಹಿತಿ' : 'Graduation Status',
    family: isKannada ? 'ಕುಟುಂಬ' : 'Family & Background',
    identity: isKannada ? 'ಗುರುತು' : 'Personal Identity',
    contact: isKannada ? 'ಸಂಪರ್ಕ' : 'Contact Details',
    address: isKannada ? 'ವಿಳಾಸ' : 'Address',
    branch: isKannada ? 'ಶೈಕ್ಷಣಿಕ ವಿವರ' : 'Academic Details',
    other: isKannada ? 'ಇತರೆ' : 'Other Information',
  };

  return (
    <div className="space-y-8">
      {Object.values(students).map((student, idx) => {
        const grad = student.graduation || {};
        const hasGrad = grad.graduation_year || grad.graduation_status || grad.student_type;

        // Group personal fields by section
        const grouped = { family: {}, identity: {}, contact: {}, address: {}, other: {} };
        for (const [k, v] of Object.entries(student.personal)) {
          const g = getFieldGroup(k);
          if (grouped[g]) grouped[g][k] = v;
          else grouped.other[k] = v;
        }

        const hasPersonalInfo = Object.values(student.personal).some(v => v !== null && v !== undefined && v !== '');
        const hasAcademicData = student.academic.length > 0;
        const hasAcademicMeta = Object.values(student.academicMeta).some(v => v !== null && v !== undefined && v !== '');

        return (
          <div key={idx} className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-sm">

            {/* ── Student Header ── */}
            <div className="p-6 pb-4 bg-gradient-to-br from-blue-50 via-slate-50 to-white border-b border-slate-100">
              <div className="flex items-start gap-4">
                {/* Avatar */}
                <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 text-white flex items-center justify-center text-2xl font-bold shadow-lg flex-shrink-0">
                  {(student.name || '?').charAt(0).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <h2 className="text-xl font-bold text-slate-800">{student.name || '—'}</h2>
                  <div className="flex flex-wrap items-center gap-2 mt-1">
                    {student.usn && (
                      <span className="px-2.5 py-0.5 bg-slate-100 rounded-md border border-slate-200 font-mono text-xs font-semibold text-slate-700">
                        {student.usn}
                      </span>
                    )}
                    {grad.graduation_status && <GradBadge status={grad.graduation_status} />}
                    {grad.student_type && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-purple-50 text-purple-700 border border-purple-100">
                        <Shield className="w-3 h-3" />
                        {grad.student_type}
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {/* Quick stats row */}
              {hasAcademicMeta && (
                <div className="mt-4 flex flex-wrap gap-3">
                  {student.academicMeta.branch && (
                    <div className="flex items-center gap-1.5 text-xs text-slate-600 bg-white px-3 py-1.5 rounded-lg border border-slate-200">
                      <BookOpen className="w-3.5 h-3.5 text-blue-500" />
                      <span className="font-semibold">{student.academicMeta.branch}</span>
                    </div>
                  )}
                  {(student.academicMeta.division || student.academicMeta.section) && (
                    <div className="flex items-center gap-1.5 text-xs text-slate-600 bg-white px-3 py-1.5 rounded-lg border border-slate-200">
                      <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
                      Section: <span className="font-semibold">{student.academicMeta.division || student.academicMeta.section}</span>
                    </div>
                  )}
                  {(student.academicMeta.current_sem || student.academicMeta.estimated_semester) && (
                    <div className="flex items-center gap-1.5 text-xs text-slate-600 bg-white px-3 py-1.5 rounded-lg border border-slate-200">
                      <BookOpen className="w-3.5 h-3.5 text-indigo-500" />
                      Sem: <span className="font-semibold">{student.academicMeta.current_sem || student.academicMeta.estimated_semester}</span>
                    </div>
                  )}
                  {(student.academicMeta.admission_year || student.academicMeta.year_of_joining) && (
                    <div className="flex items-center gap-1.5 text-xs text-slate-600 bg-white px-3 py-1.5 rounded-lg border border-slate-200">
                      <Calendar className="w-3.5 h-3.5 text-amber-500" />
                      Batch: <span className="font-semibold">{student.academicMeta.admission_year || student.academicMeta.year_of_joining}</span>
                    </div>
                  )}
                  {grad.graduation_year && (
                    <div className="flex items-center gap-1.5 text-xs text-slate-600 bg-white px-3 py-1.5 rounded-lg border border-slate-200">
                      <GraduationCap className="w-3.5 h-3.5 text-green-500" />
                      Grad: <span className="font-semibold">{grad.graduation_year}</span>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* ── Personal Information Grid ── */}
            <div className="p-6 border-b border-slate-100">
              <h3 className="text-sm font-bold text-slate-700 mb-4 flex items-center gap-2">
                <User className="w-4 h-4 text-blue-500" />
                {LABELS.personal}
                {!hasPersonalInfo && (
                  <span className="text-xs font-normal text-slate-400 italic ml-2 flex items-center gap-1">
                    <AlertCircle className="w-3 h-3" /> {isKannada ? 'ಮಾಹಿತಿ ಲಭ್ಯವಿಲ್ಲ' : 'Not available'}
                  </span>
                )}
              </h3>

              {hasPersonalInfo ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {/* Family & Background */}
                  {Object.keys(grouped.family).length > 0 && (
                    <Section title={LABELS.family} icon={<User className="w-3 h-3" />}>
                      {Object.entries(grouped.family).map(([k, v]) => (
                        <InfoRow key={k} label={prettyLabel(k)} value={prettyValue(k, v)} icon={FIELD_ICONS[k]} />
                      ))}
                    </Section>
                  )}

                  {/* Personal Identity */}
                  {Object.keys(grouped.identity).length > 0 && (
                    <Section title={LABELS.identity} icon={<Shield className="w-3 h-3" />}>
                      {Object.entries(grouped.identity).map(([k, v]) => (
                        <InfoRow key={k} label={prettyLabel(k)} value={prettyValue(k, v)} icon={FIELD_ICONS[k]} />
                      ))}
                    </Section>
                  )}

                  {/* Contact Details */}
                  {Object.keys(grouped.contact).length > 0 && (
                    <Section title={LABELS.contact} icon={<Phone className="w-3 h-3" />}>
                      {Object.entries(grouped.contact).map(([k, v]) => (
                        <InfoRow key={k} label={prettyLabel(k)} value={prettyValue(k, v)} icon={FIELD_ICONS[k] || <Phone className="w-3.5 h-3.5 text-slate-400" />} />
                      ))}
                    </Section>
                  )}

                  {/* Address */}
                  {Object.keys(grouped.address).length > 0 && (
                    <Section title={LABELS.address} icon={<MapPin className="w-3 h-3" />}>
                      {Object.entries(grouped.address).map(([k, v]) => (
                        <InfoRow key={k} label={prettyLabel(k)} value={prettyValue(k, v)} icon={FIELD_ICONS[k] || <MapPin className="w-3.5 h-3.5 text-slate-400" />} />
                      ))}
                    </Section>
                  )}

                  {/* Other additional fields */}
                  {Object.keys(grouped.other).length > 0 && (
                    <Section title={LABELS.other} icon={<ChevronRight className="w-3 h-3" />}>
                      {Object.entries(grouped.other).map(([k, v]) => (
                        <InfoRow key={k} label={prettyLabel(k)} value={prettyValue(k, v)} />
                      ))}
                    </Section>
                  )}
                </div>
              ) : (
                <p className="text-sm text-slate-400 italic flex items-center gap-2 py-4">
                  <AlertCircle className="w-4 h-4" />
                  {isKannada ? 'ವೈಯಕ್ತಿಕ ಮಾಹಿತಿ ಲಭ್ಯವಿಲ್ಲ' : 'Personal information not available for this student.'}
                </p>
              )}
            </div>

            {/* ── Graduation Status Section ── */}
            {hasGrad && (
              <div className="px-6 py-4 bg-gradient-to-r from-green-50 to-emerald-50 border-b border-green-100">
                <h3 className="text-xs font-bold text-slate-700 mb-3 flex items-center gap-2 uppercase tracking-wide">
                  <GraduationCap className="w-3.5 h-3.5 text-green-600" />
                  {LABELS.graduation}
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  {grad.student_type && (
                    <div className="text-center">
                      <p className="text-[10px] text-slate-500 uppercase tracking-wide">Type</p>
                      <p className="text-sm font-semibold text-slate-800 mt-0.5">{grad.student_type}</p>
                    </div>
                  )}
                  {(grad.admission_batch) && (
                    <div className="text-center">
                      <p className="text-[10px] text-slate-500 uppercase tracking-wide">Admission Batch</p>
                      <p className="text-sm font-semibold text-slate-800 mt-0.5">{grad.admission_batch}</p>
                    </div>
                  )}
                  {grad.graduation_year && (
                    <div className="text-center">
                      <p className="text-[10px] text-slate-500 uppercase tracking-wide">Graduation Year</p>
                      <p className="text-sm font-bold text-green-700 mt-0.5">{grad.graduation_year}</p>
                    </div>
                  )}
                  {grad.graduation_status && (
                    <div className="text-center">
                      <p className="text-[10px] text-slate-500 uppercase tracking-wide">Status</p>
                      <div className="mt-0.5 flex justify-center">
                        <GradBadge status={grad.graduation_status} />
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* ── Academic Section ── */}
            <div className="p-5 bg-white">
              <h3 className="text-xs font-bold text-slate-700 mb-3 flex items-center gap-2 uppercase tracking-wide">
                <BookOpen className="w-3.5 h-3.5 text-indigo-500" />
                {LABELS.academic}
                {!hasAcademicData && (
                  <span className="text-xs font-normal text-slate-400 italic ml-2 flex items-center gap-1">
                    <AlertCircle className="w-3 h-3" /> {isKannada ? 'ಮಾಹಿತಿ ಲಭ್ಯವಿಲ್ಲ' : 'No academic records'}
                  </span>
                )}
              </h3>
              {hasAcademicData ? (
                <GpaTable data={student.academic} />
              ) : (
                <p className="text-sm text-slate-400 italic flex items-center gap-2 py-2">
                  <AlertCircle className="w-4 h-4" />
                  {isKannada ? 'ಶೈಕ್ಷಣಿಕ ಮಾಹಿತಿ ಲಭ್ಯವಿಲ್ಲ' : 'No academic records found for this student.'}
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
