import React, { useState, useEffect } from 'react';
import GpaTable from './GpaTable';
import api from '../services/api';
import { EditFieldModal, EditFeesModal } from './StudentEditor';
import {
  User, Phone, MapPin, Mail, Droplet, Calendar,
  GraduationCap, BookOpen, Shield, AlertCircle, ChevronRight,
  Home, Briefcase, CreditCard, FileWarning, Leaf, Info, Pencil, IndianRupee
} from 'lucide-react';

// ── Academic-only keys (never shown in personal section) ─────────────────────
const isAcademicKey = (k) => {
  const lower = k.toLowerCase();
  return (
    ['semester', 'sgpa', 'cgpa', 'year'].includes(lower) ||
    /^sem_\d+_(sgpa|cgpa)$/i.test(lower) ||
    /fld_.*(sgpa|cgpa)/i.test(lower)
  );
};

// Keys shown elsewhere or skip from generic display
const SKIP_KEYS = new Set([
  'usn', 'name', 'student_id', 'created_at', 'updated_at',
  'extra_column', 'source_file', 'fld_3rd_sem_sgpa',
  'admission_batch', 'current_year', 'student_type',
  'graduation_year', 'graduation_status', 'estimated_semester',
]);

const isSkip = (k) =>
  SKIP_KEYS.has(k) || SKIP_KEYS.has(k.toLowerCase()) ||
  isAcademicKey(k) || k.startsWith('phone_') || k.startsWith('mobile_');

// ── Field label map ───────────────────────────────────────────────────────────
const FIELD_LABELS = {
  dob: 'Date of Birth',
  blood_group: 'Blood Group',
  aadhar_no: 'Aadhar No',
  father_name: "Father's Name",
  mother_name: "Mother's Name",
  father_occupation: "Father's Occupation",
  mother_occupation: "Mother's Occupation",
  parents_phone: 'Parents Phone',
  emergency_contact_number: 'Emergency Contact',
  permanent_address: 'Permanent Address',
  current_address: 'Current Address',
  year_of_joining: 'Joining Year',
  admission_year: 'Admission Year',
  year_and_branch: 'Year & Branch',
  current_sem: 'Current Semester',
  area_type: 'Area Type',
  hk_status: 'HK / Non-HK Status',
  quota: 'Admission Quota',
  distance_from_college: 'Distance from College',
  kannada_medium: 'Kannada Medium',
  physically_handicapped: 'Physically Handicapped',
  snq_quota: 'SNQ Quota',
  pin_code: 'PIN Code',
  post_office: 'Post Office',
  backlogs: 'Backlogs',
};

function prettyLabel(key) {
  return FIELD_LABELS[key] || key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function prettyValue(key, val) {
  if (val === null || val === undefined || val === '' || val === '—') return null;
  const s = String(val).trim();
  if (!s || s === 'None' || s === 'null' || s === 'undefined' || s === 'nan') return null;
  if (key === 'dob' || key === 'date_of_birth') {
    try {
      return new Date(s).toLocaleDateString('en-IN', {
        year: 'numeric', month: 'short', day: '2-digit',
      });
    } catch { return s; }
  }
  if (key === 'blood_group') return s.toUpperCase();
  if (key === 'area_type') return s.toUpperCase();
  if (key === 'hk_status') return s;
  return s;
}

function hasVal(v) {
  const s = prettyValue('', v);
  return s !== null && s !== undefined && s !== '';
}

// ── Graduation badge ──────────────────────────────────────────────────────────
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

// ── InfoRow — renders nothing when value is null/empty ────────────────────────
function InfoRow({ label, value, icon }) {
  const v = prettyValue(label.toLowerCase().replace(/ /g, '_'), value);
  if (!v) return null;
  return (
    <div className="flex items-start justify-between border-b border-slate-50 pb-1.5 gap-2">
      <span className="text-slate-500 flex items-center gap-1.5 flex-shrink-0 text-xs whitespace-nowrap">
        {icon}{label}
      </span>
      <span className="font-medium text-slate-800 text-xs text-right break-words max-w-[62%]">{v}</span>
    </div>
  );
}

// ── Section — auto-hides when no children render ──────────────────────────────
function Section({ title, icon, children, className = '' }) {
  const childArr = React.Children.toArray(children).filter(Boolean);
  if (!childArr.length) return null;
  return (
    <div className={`space-y-2 ${className}`}>
      <h3 className="text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
        {icon}{title}
      </h3>
      <div className="flex flex-col gap-1.5">{children}</div>
    </div>
  );
}

// ── Fee status badge ──────────────────────────────────────────────────────────
function FeeBadge({ status }) {
  if (!status) return <span className="text-slate-300 text-xs">—</span>;
  const s = String(status).toLowerCase();
  const isPaid = s.includes('paid') && !s.includes('not') && !s.includes('partial');
  const isNotPaid = s.includes('not paid');
  const isPartial = s.includes('partial');
  const cls = isPaid
    ? 'bg-green-100 text-green-700 border-green-200'
    : isNotPaid
    ? 'bg-red-100 text-red-700 border-red-200'
    : isPartial
    ? 'bg-amber-100 text-amber-700 border-amber-200'
    : 'bg-slate-100 text-slate-600 border-slate-200';
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold border ${cls}`}>
      {isPaid ? '✓ Paid' : isNotPaid ? '✗ Not Paid' : isPartial ? '~ Partial' : status}
    </span>
  );
}

// ── Fees sub-component — fetches from student_fees API ───────────────────────
function FeesSection({ usn, nonce = 0 }) {
  const [fees, setFees] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!usn) { setLoading(false); return; }
    api.get(`/query/students/${usn}/fees`)
      .then(r => setFees(r.data))
      .catch(() => setFees([]))
      .finally(() => setLoading(false));
  }, [usn, nonce]);

  if (loading) return <p className="text-xs text-slate-400 italic">Loading fees…</p>;
  if (!fees?.length) return null;

  // Group by fee_type
  const grouped = {};
  for (const f of fees) {
    const key = f.fee_type || 'OTHER';
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(f);
  }

  const FEE_LABELS = {
    VTU: 'VTU Fees',
    PD: 'PD Fees',
    IDP: 'IDP / Tuition Fees',
    TUITION_PAID: 'Tuition Fees Paid',
    TUITION_REMAINING: 'Tuition Remaining',
  };

  return (
    <div className="space-y-3">
      {Object.entries(grouped).map(([feeType, rows]) => (
        <div key={feeType}>
          <p className="text-[10px] font-bold text-slate-500 uppercase mb-1.5">
            {FEE_LABELS[feeType] || feeType}
          </p>
          <div className="grid grid-cols-3 gap-2">
            {rows
              .sort((a, b) => (a.year || 0) - (b.year || 0))
              .map((f, i) => (
                <div key={i} className="bg-slate-50 rounded-lg p-2 border border-slate-100 text-center">
                  {f.year > 0 && (
                    <p className="text-[9px] text-slate-400 uppercase mb-1">Year {f.year}</p>
                  )}
                  <FeeBadge status={f.status} />
                  {f.amount_paid && !['paid', 'not paid', 'partially paid'].includes(
                    String(f.amount_paid).toLowerCase()
                  ) && (
                    <p className="text-[9px] text-slate-500 mt-0.5">₹ {f.amount_paid}</p>
                  )}
                </div>
              ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Backlogs sub-component — fetches from student_backlogs API ────────────────
function BacklogsSection({ usn, rawText }) {
  const [backlogs, setBacklogs] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!usn) { setLoading(false); return; }
    api.get(`/query/students/${usn}/backlogs`)
      .then(r => setBacklogs(r.data))
      .catch(() => setBacklogs([]))
      .finally(() => setLoading(false));
  }, [usn]);

  if (loading) return <p className="text-xs text-slate-400 italic">Loading backlogs…</p>;

  // If API returned structured data, use it; otherwise fall back to raw text
  const hasStructured = backlogs?.length > 0;
  const hasRaw = rawText && String(rawText).trim() &&
    !['no', 'none', '0', 'nil', 'na', 'not applicable', 'zero', 'null'].includes(
      String(rawText).trim().toLowerCase()
    );

  if (!hasStructured && !hasRaw) {
    return (
      <div className="flex items-center gap-2 px-3 py-2 bg-green-50 rounded-lg border border-green-100">
        <span className="text-green-600 text-xs font-semibold">✓ No backlogs</span>
      </div>
    );
  }

  if (hasStructured) {
    return (
      <div className="space-y-1.5">
        {backlogs.map((b, i) => (
          <div key={i} className="flex items-start gap-2 px-3 py-2 bg-amber-50 rounded-lg border border-amber-100">
            <FileWarning className="w-3.5 h-3.5 text-amber-500 flex-shrink-0 mt-0.5" />
            <div className="min-w-0">
              <p className="text-xs font-semibold text-slate-800 truncate">{b.subject}</p>
              {(b.semester || b.year) && (
                <p className="text-[10px] text-slate-500">
                  {b.semester ? `Sem ${b.semester}` : ''}{b.semester && b.year ? ' · ' : ''}{b.year || ''}
                </p>
              )}
            </div>
            {b.cleared === 1 && (
              <span className="ml-auto text-[10px] text-green-600 font-semibold flex-shrink-0">Cleared</span>
            )}
          </div>
        ))}
      </div>
    );
  }

  // Fallback: raw text
  return (
    <div className="px-3 py-2 bg-amber-50 rounded-lg border border-amber-100">
      <p className="text-xs text-slate-700 whitespace-pre-wrap break-words">{String(rawText).trim()}</p>
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────
export default function CombinedStudentView({ data, responseLanguage }) {
  const [editor, setEditor] = useState(null); // {type:'field'|'fees', usn, name}
  const [nonce, setNonce] = useState(0); // bump to refetch live fee/backlog sections after a save
  const role = (typeof localStorage !== 'undefined' ? (localStorage.getItem('role') || '') : '').toLowerCase();
  const canEdit = role === 'staff' || role === 'admin';
  const isAdmin = role === 'admin';

  if (!data?.length) return null;

  const isKannada = responseLanguage === 'kannada' || responseLanguage === 'mixed';

  // ── Group data rows by student USN ────────────────────────────────────────
  const studentsMap = new Map();

  for (const row of data) {
    const key = row.usn || row.name || 'Unknown';
    if (!studentsMap.has(key)) {
      const personal = {};
      const academic_meta = {};
      const ACADEMIC_META_KEYS = new Set([
        'branch', 'division', 'section', 'domain',
        'year_and_branch', 'year_of_joining', 'admission_year', 'current_sem',
      ]);

      for (const [k, v] of Object.entries(row)) {
        if (isSkip(k)) continue;
        if (ACADEMIC_META_KEYS.has(k.toLowerCase())) {
          academic_meta[k] = v;
        } else {
          personal[k] = v;
        }
      }

      studentsMap.set(key, {
        usn: row.usn,
        name: row.name,
        personal,
        academic_meta,
        graduation: {
          graduation_year: row.graduation_year,
          graduation_status: row.graduation_status,
          student_type: row.student_type,
          admission_batch: row.admission_batch ?? row.admission_year,
          current_year: row.current_year,
          current_sem: row.current_sem,
        },
        academic_rows: [],
      });
    }

    const stu = studentsMap.get(key);
    if (row.semester != null || row.sgpa != null) {
      stu.academic_rows.push(row);
    }
    if (row.graduation_year && !stu.graduation.graduation_year) {
      stu.graduation.graduation_year = row.graduation_year;
      stu.graduation.graduation_status = row.graduation_status;
    }
  }

  return (
    <div className="space-y-6">
      {[...studentsMap.values()].map((student, idx) => {
        const grad = student.graduation;
        const p = student.personal;
        const am = student.academic_meta;
        const hasAcademic = student.academic_rows.length > 0;

        // ── Categorise personal fields ─────────────────────────────────────
        // Family: names + religion/caste (only non-null)
        const familyNameFields    = ['father_name', 'mother_name', 'guardian_name'];
        const parentOccupFields   = ['father_occupation', 'mother_occupation'];
        const religionFields      = ['religion', 'caste', 'sub_caste', 'category'];
        const identityFields      = ['dob', 'gender', 'blood_group', 'aadhar_no', 'status'];
        const contactFields       = ['phone', 'parents_phone', 'emergency_contact_number', 'email'];
        const addressSpecific     = ['village', 'area_type', 'area', 'region', 'taluk', 'district', 'state', 'pin_code', 'post_office'];
        const admissionInfoFields = ['hk_status', 'quota', 'distance_from_college', 'kannada_medium', 'physically_handicapped', 'snq_quota'];
        const backlogs_raw        = p.backlogs;

        const anyPersonal = Object.values(p).some(v => hasVal(v));

        return (
          <div key={idx} className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-sm">

            {/* ── Student Header ───────────────────────────────────────────── */}
            <div className="p-5 pb-4 bg-gradient-to-br from-blue-50 to-slate-50 border-b border-slate-100">
              <div className="flex items-start gap-4">
                <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 text-white flex items-center justify-center text-2xl font-bold shadow-md flex-shrink-0">
                  {(student.name || '?').charAt(0).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <h2 className="text-lg font-bold text-slate-800">{student.name || '—'}</h2>
                  <div className="flex flex-wrap items-center gap-2 mt-1">
                    {student.usn && (
                      <span className="px-2.5 py-0.5 bg-slate-100 rounded-md border border-slate-200 font-mono text-xs font-semibold text-slate-700">
                        {student.usn}
                      </span>
                    )}
                    {grad.graduation_status && <GradBadge status={grad.graduation_status} />}
                    {grad.student_type && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-purple-50 text-purple-700 border border-purple-100">
                        <Shield className="w-3 h-3" />{grad.student_type}
                      </span>
                    )}
                    {p.hk_status && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-orange-50 text-orange-700 border border-orange-100">
                        {p.hk_status}
                      </span>
                    )}
                    {p.area_type && (
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border ${
                        String(p.area_type).toUpperCase() === 'RURAL'
                          ? 'bg-green-50 text-green-700 border-green-100'
                          : 'bg-blue-50 text-blue-700 border-blue-100'
                      }`}>
                        <Leaf className="w-3 h-3" />
                        {String(p.area_type).toUpperCase()}
                      </span>
                    )}
                  </div>
                </div>
                {canEdit && student.usn && (
                  <div className="flex flex-col gap-1.5 flex-shrink-0">
                    <button
                      onClick={() => setEditor({ type: 'field', usn: student.usn, name: student.name })}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] font-semibold rounded-lg border border-blue-200 bg-white text-blue-700 hover:bg-blue-50 transition-colors">
                      <Pencil className="w-3 h-3" />Edit details
                    </button>
                    {isAdmin && (
                      <button
                        onClick={() => setEditor({ type: 'fees', usn: student.usn, name: student.name })}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] font-semibold rounded-lg border border-emerald-200 bg-white text-emerald-700 hover:bg-emerald-50 transition-colors">
                        <IndianRupee className="w-3 h-3" />Edit fees
                      </button>
                    )}
                  </div>
                )}
              </div>

              {/* Academic chips */}
              <div className="mt-3 flex flex-wrap gap-2">
                {am.branch && (
                  <div className="flex items-center gap-1.5 text-xs text-slate-600 bg-white px-2.5 py-1 rounded-lg border border-slate-200">
                    <BookOpen className="w-3 h-3 text-blue-500" />
                    <span className="font-semibold">{am.branch}</span>
                  </div>
                )}
                {(am.division || am.section) && (
                  <div className="flex items-center gap-1.5 text-xs text-slate-600 bg-white px-2.5 py-1 rounded-lg border border-slate-200">
                    Section: <span className="font-semibold ml-1">{am.division || am.section}</span>
                  </div>
                )}
                {(am.current_sem || grad.current_sem) && (
                  <div className="flex items-center gap-1.5 text-xs text-slate-600 bg-white px-2.5 py-1 rounded-lg border border-slate-200">
                    <BookOpen className="w-3 h-3 text-indigo-400" />
                    Sem: <span className="font-semibold ml-1">{am.current_sem || grad.current_sem}</span>
                  </div>
                )}
                {(am.admission_year || am.year_of_joining || grad.admission_batch) && (
                  <div className="flex items-center gap-1.5 text-xs text-slate-600 bg-white px-2.5 py-1 rounded-lg border border-slate-200">
                    <Calendar className="w-3 h-3 text-amber-400" />
                    Batch: <span className="font-semibold ml-1">{am.admission_year || am.year_of_joining || grad.admission_batch}</span>
                  </div>
                )}
                {grad.graduation_year && (
                  <div className="flex items-center gap-1.5 text-xs text-slate-600 bg-white px-2.5 py-1 rounded-lg border border-slate-200">
                    <GraduationCap className="w-3 h-3 text-green-500" />
                    Grad: <span className="font-semibold ml-1">{grad.graduation_year}</span>
                  </div>
                )}
              </div>
            </div>

            {/* ── Personal Information ─────────────────────────────────────── */}
            <div className="p-5 border-b border-slate-100">
              <h3 className="text-xs font-bold text-slate-600 mb-4 flex items-center gap-2 uppercase tracking-wide">
                <User className="w-3.5 h-3.5 text-blue-500" />
                {isKannada ? 'ವೈಯಕ್ತಿಕ ಮಾಹಿತಿ' : 'Personal Information'}
              </h3>
              {anyPersonal ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">

                  {/* Family — Names only */}
                  <Section title={isKannada ? 'ಕುಟುಂಬ' : 'Family & Background'} icon={<User className="w-3 h-3" />}>
                    {familyNameFields.map(k => (
                      <InfoRow key={k} label={prettyLabel(k)} value={p[k]} />
                    ))}
                    {religionFields.map(k => (
                      <InfoRow key={k} label={prettyLabel(k)} value={p[k]} />
                    ))}
                  </Section>

                  {/* Parents' Occupation — NEW SECTION */}
                  <Section
                    title={isKannada ? 'ಪಾಲಕರ ವೃತ್ತಿ' : "Parents' Occupation"}
                    icon={<Briefcase className="w-3 h-3" />}
                  >
                    {parentOccupFields.map(k => (
                      <InfoRow key={k} label={prettyLabel(k)} value={p[k]} icon={<Briefcase className="w-3 h-3 text-slate-400" />} />
                    ))}
                    <InfoRow label="Parents Phone" value={p.parents_phone} icon={<Phone className="w-3 h-3 text-slate-400" />} />
                  </Section>

                  {/* Personal Identity */}
                  <Section title={isKannada ? 'ಗುರುತು' : 'Personal Identity'} icon={<Shield className="w-3 h-3" />}>
                    {identityFields.map(k => (
                      <InfoRow
                        key={k}
                        label={prettyLabel(k)}
                        value={p[k]}
                        icon={
                          k === 'blood_group' ? <Droplet className="w-3 h-3 text-red-400" /> :
                          k === 'dob' ? <Calendar className="w-3 h-3 text-slate-400" /> : null
                        }
                      />
                    ))}
                  </Section>

                  {/* Contact */}
                  <Section title={isKannada ? 'ಸಂಪರ್ಕ' : 'Contact Details'} icon={<Phone className="w-3 h-3" />}>
                    {contactFields.map(k => (
                      <InfoRow key={k} label={prettyLabel(k)} value={p[k]} icon={<Phone className="w-3 h-3 text-slate-400" />} />
                    ))}
                  </Section>

                  {/* Address */}
                  <Section title={isKannada ? 'ವಿಳಾಸ' : 'Address'} icon={<MapPin className="w-3 h-3" />}>
                    {(p.permanent_address || p.address) && (
                      <InfoRow
                        label={p.permanent_address ? 'Permanent Address' : 'Address'}
                        value={p.permanent_address || p.address}
                        icon={<Home className="w-3 h-3 text-slate-400" />}
                      />
                    )}
                    {p.current_address && p.current_address !== (p.permanent_address || p.address) && (
                      <InfoRow label="Current Address" value={p.current_address} icon={<MapPin className="w-3 h-3 text-slate-400" />} />
                    )}
                    {addressSpecific.map(k => (
                      <InfoRow key={k} label={prettyLabel(k)} value={p[k]} icon={<MapPin className="w-3 h-3 text-slate-400" />} />
                    ))}
                  </Section>

                  {/* Admission / Other Info — NEW SECTION */}
                  <Section title={isKannada ? 'ಪ್ರವೇಶ ವಿವರ' : 'Admission Details'} icon={<Info className="w-3 h-3" />}>
                    {admissionInfoFields.map(k => (
                      <InfoRow key={k} label={prettyLabel(k)} value={p[k]} />
                    ))}
                  </Section>

                </div>
              ) : (
                <p className="text-sm text-slate-400 italic flex items-center gap-2 py-3">
                  <AlertCircle className="w-4 h-4" />
                  {isKannada ? 'ವೈಯಕ್ತಿಕ ಮಾಹಿತಿ ಲಭ್ಯವಿಲ್ಲ' : 'Personal information not available.'}
                </p>
              )}
            </div>

            {/* ── Graduation Status ────────────────────────────────────────── */}
            {(grad.graduation_status || grad.graduation_year || grad.student_type) && (
              <div className="px-5 py-3 bg-gradient-to-r from-green-50 to-emerald-50 border-b border-green-100">
                <h3 className="text-xs font-bold text-slate-600 mb-2 flex items-center gap-2 uppercase tracking-wide">
                  <GraduationCap className="w-3.5 h-3.5 text-green-600" />
                  {isKannada ? 'ಪದವಿ ಮಾಹಿತಿ' : 'Graduation Status'}
                </h3>
                <div className="flex flex-wrap gap-4">
                  {grad.student_type && (
                    <div>
                      <p className="text-[10px] text-slate-500 uppercase">Type</p>
                      <p className="text-sm font-semibold">{grad.student_type}</p>
                    </div>
                  )}
                  {grad.admission_batch && (
                    <div>
                      <p className="text-[10px] text-slate-500 uppercase">Admission Batch</p>
                      <p className="text-sm font-semibold">{grad.admission_batch}</p>
                    </div>
                  )}
                  {grad.graduation_year && (
                    <div>
                      <p className="text-[10px] text-slate-500 uppercase">Graduation Year</p>
                      <p className="text-sm font-bold text-green-700">{grad.graduation_year}</p>
                    </div>
                  )}
                  {grad.graduation_status && (
                    <div>
                      <p className="text-[10px] text-slate-500 uppercase">Status</p>
                      <GradBadge status={grad.graduation_status} />
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* ── Academic Information — SGPA / Marks ─────────────────────── */}
            <div className="p-5 border-b border-slate-100">
              <h3 className="text-xs font-bold text-slate-600 mb-3 flex items-center gap-2 uppercase tracking-wide">
                <BookOpen className="w-3.5 h-3.5 text-indigo-500" />
                {isKannada ? 'ಶೈಕ್ಷಣಿಕ ಮಾಹಿತಿ' : 'Academic Information'}
                {!hasAcademic && (
                  <span className="text-xs font-normal text-slate-400 italic ml-2 flex items-center gap-1">
                    <AlertCircle className="w-3 h-3" />
                    {isKannada ? 'ಲಭ್ಯವಿಲ್ಲ' : 'No academic records'}
                  </span>
                )}
              </h3>
              {hasAcademic ? (
                <GpaTable data={student.academic_rows} />
              ) : (
                <p className="text-sm text-slate-400 italic flex items-center gap-2 py-1">
                  <AlertCircle className="w-4 h-4" />
                  {isKannada ? 'ಶೈಕ್ಷಣಿಕ ಮಾಹಿತಿ ಲಭ್ಯವಿಲ್ಲ' : 'No academic records found.'}
                </p>
              )}
            </div>

            {/* ── Backlogs — NEW SECTION ───────────────────────────────────── */}
            <div className="p-5 border-b border-slate-100">
              <h3 className="text-xs font-bold text-slate-600 mb-3 flex items-center gap-2 uppercase tracking-wide">
                <FileWarning className="w-3.5 h-3.5 text-amber-500" />
                {isKannada ? 'ಬ್ಯಾಕ್‌ಲಾಗ್‌ಗಳು' : 'Backlogs / Arrears'}
              </h3>
              <BacklogsSection usn={student.usn} rawText={backlogs_raw} />
            </div>

            {/* ── Fees — NEW SECTION ───────────────────────────────────────── */}
            <div className="p-5">
              <h3 className="text-xs font-bold text-slate-600 mb-3 flex items-center gap-2 uppercase tracking-wide">
                <CreditCard className="w-3.5 h-3.5 text-violet-500" />
                {isKannada ? 'ಶುಲ್ಕ ಮಾಹಿತಿ' : 'Fee Details'}
              </h3>
              <FeesSection usn={student.usn} nonce={nonce} />
            </div>

          </div>
        );
      })}

      {editor?.type === 'field' && (
        <EditFieldModal
          usn={editor.usn}
          name={editor.name}
          onClose={() => setEditor(null)}
          onSaved={() => setNonce(n => n + 1)}
        />
      )}
      {editor?.type === 'fees' && (
        <EditFeesModal
          usn={editor.usn}
          name={editor.name}
          onClose={() => setEditor(null)}
          onSaved={() => setNonce(n => n + 1)}
        />
      )}
    </div>
  );
}
