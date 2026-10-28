import React, { useState, useEffect } from 'react';
import GpaTable from './GpaTable';
import api from '../services/api';
import { EditFieldModal, EditFeesModal } from './StudentEditor';
import { useI18n } from '../context/LanguageContext';
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
// Keys are DB column names and are load-bearing (prettyValue/InfoRow match on
// them) — never renamed. Values are i18n keys for the label shown beside the
// value. Columns not listed here fall through to their raw field name, which is
// an API field name and therefore deliberately not translated.
const FIELD_LABELS = {
  dob: 'student.field.dob',
  blood_group: 'student.field.bloodGroup',
  aadhar_no: 'student.field.aadharNo',
  father_name: 'student.field.fatherName',
  mother_name: 'student.field.motherName',
  father_occupation: 'student.field.fatherOccupation',
  mother_occupation: 'student.field.motherOccupation',
  parents_phone: 'student.field.parentsPhone',
  emergency_contact_number: 'student.field.emergencyContact',
  permanent_address: 'student.field.permanentAddress',
  current_address: 'student.field.currentAddress',
  year_of_joining: 'student.field.joiningYear',
  admission_year: 'student.field.admissionYear',
  year_and_branch: 'student.field.yearAndBranch',
  current_sem: 'student.field.currentSem',
  area_type: 'student.field.areaType',
  hk_status: 'student.field.hkStatus',
  quota: 'student.field.quota',
  distance_from_college: 'student.field.distanceFromCollege',
  kannada_medium: 'student.field.kannadaMedium',
  physically_handicapped: 'student.field.physicallyHandicapped',
  snq_quota: 'student.field.snqQuota',
  pin_code: 'student.field.pinCode',
  post_office: 'student.field.postOffice',
  backlogs: 'student.field.backlogs',
  // English values below are byte-identical to the pretty-case fallback that
  // used to render them, so adding them only brings Kannada coverage.
  gender: 'student.field.gender',
  status: 'common.status',
  email: 'student.field.email',
  phone: 'student.field.phone',
  guardian_name: 'student.field.guardianName',
  religion: 'student.field.religion',
  caste: 'student.field.caste',
  sub_caste: 'student.field.subCaste',
  category: 'student.field.category',
  village: 'student.field.village',
  area: 'student.field.area',
  region: 'student.field.region',
  taluk: 'student.field.taluk',
  district: 'student.field.district',
  state: 'student.field.state',
  address: 'student.field.address',
};

function prettyLabel(key, t) {
  const labelKey = FIELD_LABELS[key];
  if (labelKey) return t(labelKey);
  return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

// ── Value handling: untouched. Statuses, names, USNs and addresses are
//    rendered exactly as the database returned them. ────────────────────────
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
  const { t } = useI18n();
  if (!status) return null;
  const isGrad = String(status).toUpperCase() === 'GRADUATED';
  return (
    <span className={`badge gap-1 ${isGrad ? 'badge-ok' : 'badge-info'}`}>
      {isGrad ? <GraduationCap className="h-3 w-3" /> : <BookOpen className="h-3 w-3" />}
      {isGrad ? t('student.graduated') : t('student.active')}
    </span>
  );
}

// ── InfoRow — renders nothing when value is null/empty ────────────────────────
function InfoRow({ label, value, icon, field }) {
  // `field` is the DB column; older callers derived it from the English label,
  // which no longer works once the label is Kannada. The fallback is kept for
  // any caller that still passes only a label.
  const key = field != null ? field : label.toLowerCase().replace(/ /g, '_');
  const v = prettyValue(key, value);
  if (!v) return null;
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 border-b border-line/70 pb-1.5 last:border-b-0">
      <span className="t-label flex flex-wrap items-center gap-1.5 text-ink-mute">
        {icon}{label}
      </span>
      <span className="t-body max-w-full break-words font-medium text-ink tabular-nums sm:max-w-[62%] sm:text-right">
        {v}
      </span>
    </div>
  );
}

// ── Section — auto-hides when no children render ──────────────────────────────
function Section({ title, icon, children, className = '' }) {
  const childArr = React.Children.toArray(children).filter(Boolean);
  if (!childArr.length) return null;
  return (
    <section className={`sunken p-3 ${className}`}>
      <h4 className="t-label mb-2 flex flex-wrap items-center gap-1.5 font-semibold uppercase tracking-wide text-ink-soft">
        {icon}{title}
      </h4>
      <div className="flex flex-col gap-1.5">{children}</div>
    </section>
  );
}

// ── Fee status badge ──────────────────────────────────────────────────────────
// Detection rules are unchanged; an unrecognised status string from the DB is
// printed exactly as stored rather than mapped to a tidier word.
function FeeBadge({ status }) {
  const { t } = useI18n();
  if (!status) return <span className="text-xs text-ink-faint">—</span>;
  const s = String(status).toLowerCase();
  const isPaid = s.includes('paid') && !s.includes('not') && !s.includes('partial');
  const isNotPaid = s.includes('not paid');
  const isPartial = s.includes('partial');
  const tone = isPaid
    ? 'badge-ok'
    : isNotPaid
    ? 'badge-err'
    : isPartial
    ? 'badge-warn'
    : 'badge-quiet';
  return (
    <span className={`badge max-w-full whitespace-normal break-words text-center ${tone}`}>
      {isPaid ? t('student.feePaid') : isNotPaid ? t('student.feeNotPaid') : isPartial ? t('student.feePartial') : status}
    </span>
  );
}

// ── Fees sub-component — fetches from student_fees API ───────────────────────
const FEE_LABELS = {
  VTU: 'student.feeVtu',
  PD: 'student.feePd',
  IDP: 'student.feeIdp',
  TUITION_PAID: 'student.feeTuitionPaid',
  TUITION_REMAINING: 'student.feeTuitionRemaining',
};

function FeesSection({ usn, nonce = 0 }) {
  const { t } = useI18n();
  const [fees, setFees] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!usn) { setLoading(false); return; }
    api.get(`/query/students/${usn}/fees`)
      .then(r => setFees(r.data))
      .catch(() => setFees([]))
      .finally(() => setLoading(false));
  }, [usn, nonce]);

  if (loading) return <p className="t-support italic text-ink-mute">{t('student.loadingFees')}</p>;
  if (!fees?.length) return null;

  // Group by fee_type
  const grouped = {};
  for (const f of fees) {
    const key = f.fee_type || 'OTHER';
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(f);
  }

  return (
    <div className="space-y-3">
      {Object.entries(grouped).map(([feeType, rows]) => (
        <div key={feeType}>
          <p className="t-label mb-1.5 flex flex-wrap items-center gap-1.5 font-semibold uppercase tracking-wide text-ink-soft">
            {FEE_LABELS[feeType] ? t(FEE_LABELS[feeType]) : feeType}
          </p>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {rows
              .sort((a, b) => (a.year || 0) - (b.year || 0))
              .map((f, i) => (
                <div key={i} className="sunken flex flex-col items-center gap-1 p-2 text-center">
                  {f.year > 0 && (
                    <p className="text-xs uppercase text-ink-mute tabular-nums">
                      {t('student.year', { y: f.year })}
                    </p>
                  )}
                  <FeeBadge status={f.status} />
                  {f.amount_paid && !['paid', 'not paid', 'partially paid'].includes(
                    String(f.amount_paid).toLowerCase()
                  ) && (
                    <p className="text-xs text-ink-mute tabular-nums">₹ {f.amount_paid}</p>
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
  const { t } = useI18n();
  const [backlogs, setBacklogs] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!usn) { setLoading(false); return; }
    api.get(`/query/students/${usn}/backlogs`)
      .then(r => setBacklogs(r.data))
      .catch(() => setBacklogs([]))
      .finally(() => setLoading(false));
  }, [usn]);

  if (loading) return <p className="t-support italic text-ink-mute">{t('student.loadingBacklogs')}</p>;

  // If API returned structured data, use it; otherwise fall back to raw text
  const hasStructured = backlogs?.length > 0;
  const hasRaw = rawText && String(rawText).trim() &&
    !['no', 'none', '0', 'nil', 'na', 'not applicable', 'zero', 'null'].includes(
      String(rawText).trim().toLowerCase()
    );

  if (!hasStructured && !hasRaw) {
    return (
      <div className="flex flex-wrap items-center gap-2 rounded-md border border-ok/40 bg-ok-soft p-2.5">
        <span className="t-table font-semibold text-ok">{t('student.noBacklogs')}</span>
      </div>
    );
  }

  if (hasStructured) {
    return (
      <div className="space-y-1.5">
        {backlogs.map((b, i) => (
          <div key={i} className="flex flex-wrap items-start gap-2 rounded-md border border-warn/40 bg-warn-soft p-2.5">
            <FileWarning className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-warn" aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <p className="t-table break-words font-semibold text-ink">{b.subject}</p>
              {(b.semester || b.year) && (
                <p className="text-xs text-ink-mute tabular-nums">
                  {b.semester ? `${t('student.semShort')} ${b.semester}` : ''}{b.semester && b.year ? ' · ' : ''}{b.year || ''}
                </p>
              )}
            </div>
            {b.cleared === 1 && (
              <span className="ml-auto flex-shrink-0 text-xs font-semibold text-ok">
                {t('student.cleared')}
              </span>
            )}
          </div>
        ))}
      </div>
    );
  }

  // Fallback: raw text exactly as stored
  return (
    <div className="sunken p-3">
      <p className="t-body break-words whitespace-pre-wrap text-ink">{String(rawText).trim()}</p>
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────
export default function CombinedStudentView({ data, responseLanguage }) {
  const { t } = useI18n();
  const [editor, setEditor] = useState(null); // {type:'field'|'fees', usn, name}
  const [nonce, setNonce] = useState(0); // bump to refetch live fee/backlog sections after a save
  // Presentation only: the card whose save just landed is washed once in the
  // accent colour so the eye can find it in a long result set.
  const [flashUsn, setFlashUsn] = useState(null);
  useEffect(() => {
    if (!flashUsn) return undefined;
    const id = setTimeout(() => setFlashUsn(null), 1800);
    return () => clearTimeout(id);
  }, [flashUsn]);
  const role = (typeof localStorage !== 'undefined' ? (localStorage.getItem('role') || '') : '').toLowerCase();
  const canEdit = role === 'staff' || role === 'admin';
  const isAdmin = role === 'admin';

  if (!data?.length) return null;

  // `responseLanguage` is the language of the AI *answer* (Dashboard's own
  // switch), not of the interface. It still drives the Kannada font so a
  // Kannada answer stays legible when the chrome language is English.
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
          <div key={student.usn || idx} className={`card anim-fade-up overflow-hidden${flashUsn && flashUsn === student.usn ? ' row-flash' : ''}`}>

            {/* ── Student Header ───────────────────────────────────────────── */}
            <div
              lang={isKannada ? 'kn' : undefined}
              className={`border-b border-line bg-gradient-to-br from-brand/[0.07] via-surface to-surface p-4 sm:p-5 ${isKannada ? 'font-kannada' : ''}`}
            >
              <div className="flex flex-wrap items-start gap-4">
                <div className="flex h-14 w-14 flex-shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-brand-mid to-brand text-2xl font-bold text-white shadow-md">
                  {(student.name || '?').charAt(0).toUpperCase()}
                </div>
                <div className="min-w-0 flex-1">
                  <h2 className="t-card break-words text-ink">{student.name || '—'}</h2>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2">
                    {student.usn && (
                      <span className="badge badge-quiet font-mono text-xs font-semibold tabular-nums">
                        {student.usn}
                      </span>
                    )}
                    {grad.graduation_status && <GradBadge status={grad.graduation_status} />}
                    {grad.student_type && (
                      <span className="badge gap-1 badge-brand">
                        <Shield className="h-3 w-3" aria-hidden="true" />
                        <span className="max-w-full whitespace-normal break-words">{grad.student_type}</span>
                      </span>
                    )}
                    {p.hk_status && (
                      <span className="badge badge-warn max-w-full whitespace-normal break-words">
                        {p.hk_status}
                      </span>
                    )}
                    {p.area_type && (
                      <span className={`badge gap-1 ${
                        String(p.area_type).toUpperCase() === 'RURAL' ? 'badge-ok' : 'badge-info'
                      }`}>
                        <Leaf className="h-3 w-3" aria-hidden="true" />
                        {String(p.area_type).toUpperCase()}
                      </span>
                    )}
                  </div>
                </div>
                {canEdit && student.usn && (
                  <div className="flex flex-shrink-0 flex-wrap gap-1.5">
                    <button
                      type="button"
                      onClick={() => setEditor({ type: 'field', usn: student.usn, name: student.name })}
                      className="btn btn-sm btn-primary">
                      <Pencil className="h-3.5 w-3.5" aria-hidden="true" />{t('student.editDetails')}
                    </button>
                    {isAdmin && (
                      <button
                        type="button"
                        onClick={() => setEditor({ type: 'fees', usn: student.usn, name: student.name })}
                        className="btn btn-sm btn-ghost">
                        <IndianRupee className="h-3.5 w-3.5 text-ok" aria-hidden="true" />{t('student.editFees')}
                      </button>
                    )}
                  </div>
                )}
              </div>

              {/* Academic chips */}
              <div className="mt-3 flex flex-wrap gap-2">
                {am.branch && (
                  <div className="inline-flex flex-wrap items-center gap-1.5 rounded-md border border-line bg-surface px-2.5 py-1 text-xs text-ink-soft">
                    <BookOpen className="h-3.5 w-3.5 text-brand-fg" aria-hidden="true" />
                    <span className="font-semibold text-ink">{am.branch}</span>
                  </div>
                )}
                {(am.division || am.section) && (
                  <div className="inline-flex flex-wrap items-center gap-1.5 rounded-md border border-line bg-surface px-2.5 py-1 text-xs text-ink-soft">
                    {t('student.section')}<span className="ml-1 font-semibold text-ink tabular-nums">{am.division || am.section}</span>
                  </div>
                )}
                {(am.current_sem || grad.current_sem) && (
                  <div className="inline-flex flex-wrap items-center gap-1.5 rounded-md border border-line bg-surface px-2.5 py-1 text-xs text-ink-soft">
                    <BookOpen className="h-3.5 w-3.5 text-brand-fg" aria-hidden="true" />
                    {t('student.sem')}<span className="ml-1 font-semibold text-ink tabular-nums">{am.current_sem || grad.current_sem}</span>
                  </div>
                )}
                {(am.admission_year || am.year_of_joining || grad.admission_batch) && (
                  <div className="inline-flex flex-wrap items-center gap-1.5 rounded-md border border-line bg-surface px-2.5 py-1 text-xs text-ink-soft">
                    <Calendar className="h-3.5 w-3.5 text-accent-ink" aria-hidden="true" />
                    {t('student.batch')}<span className="ml-1 font-semibold text-ink tabular-nums">{am.admission_year || am.year_of_joining || grad.admission_batch}</span>
                  </div>
                )}
                {grad.graduation_year && (
                  <div className="inline-flex flex-wrap items-center gap-1.5 rounded-md border border-line bg-surface px-2.5 py-1 text-xs text-ink-soft">
                    <GraduationCap className="h-3.5 w-3.5 text-ok" aria-hidden="true" />
                    {t('student.grad')}<span className="ml-1 font-semibold text-ink tabular-nums">{grad.graduation_year}</span>
                  </div>
                )}
              </div>
            </div>

            {/* ── Personal Information ─────────────────────────────────────── */}
            <div className="border-b border-line p-4 sm:p-5">
              <h3 className="t-card mb-4 flex flex-wrap items-center gap-2 text-ink">
                <User className="h-4 w-4 text-brand-fg" aria-hidden="true" />
                {t('student.personalInfo')}
              </h3>
              {anyPersonal ? (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">

                  {/* Family — Names only */}
                  <Section title={t('student.family')} icon={<User className="h-3.5 w-3.5 text-brand-fg" aria-hidden="true" />}>
                    {familyNameFields.map(k => (
                      <InfoRow key={k} field={k} label={prettyLabel(k, t)} value={p[k]} />
                    ))}
                    {religionFields.map(k => (
                      <InfoRow key={k} field={k} label={prettyLabel(k, t)} value={p[k]} />
                    ))}
                  </Section>

                  {/* Parents' Occupation */}
                  <Section
                    title={t('student.parentsOccupation')}
                    icon={<Briefcase className="h-3.5 w-3.5 text-brand-fg" aria-hidden="true" />}
                  >
                    {parentOccupFields.map(k => (
                      <InfoRow key={k} field={k} label={prettyLabel(k, t)} value={p[k]} icon={<Briefcase className="h-3.5 w-3.5 text-ink-faint" aria-hidden="true" />} />
                    ))}
                    <InfoRow field="parents_phone" label={prettyLabel('parents_phone', t)} value={p.parents_phone} icon={<Phone className="h-3.5 w-3.5 text-ink-faint" aria-hidden="true" />} />
                  </Section>

                  {/* Personal Identity */}
                  <Section title={t('student.personalIdentity')} icon={<Shield className="h-3.5 w-3.5 text-brand-fg" aria-hidden="true" />}>
                    {identityFields.map(k => (
                      <InfoRow
                        key={k}
                        field={k}
                        label={prettyLabel(k, t)}
                        value={p[k]}
                        icon={
                          k === 'blood_group' ? <Droplet className="h-3.5 w-3.5 text-err" aria-hidden="true" /> :
                          k === 'dob' ? <Calendar className="h-3.5 w-3.5 text-ink-faint" aria-hidden="true" /> : null
                        }
                      />
                    ))}
                  </Section>

                  {/* Contact */}
                  <Section title={t('student.contact')} icon={<Phone className="h-3.5 w-3.5 text-brand-fg" aria-hidden="true" />}>
                    {contactFields.map(k => (
                      <InfoRow key={k} field={k} label={prettyLabel(k, t)} value={p[k]} icon={<Phone className="h-3.5 w-3.5 text-ink-faint" aria-hidden="true" />} />
                    ))}
                  </Section>

                  {/* Address */}
                  <Section title={t('student.address')} icon={<MapPin className="h-3.5 w-3.5 text-brand-fg" aria-hidden="true" />}>
                    {(p.permanent_address || p.address) && (
                      <InfoRow
                        field={p.permanent_address ? 'permanent_address' : 'address'}
                        label={p.permanent_address ? prettyLabel('permanent_address', t) : prettyLabel('address', t)}
                        value={p.permanent_address || p.address}
                        icon={<Home className="h-3.5 w-3.5 text-ink-faint" aria-hidden="true" />}
                      />
                    )}
                    {p.current_address && p.current_address !== (p.permanent_address || p.address) && (
                      <InfoRow field="current_address" label={prettyLabel('current_address', t)} value={p.current_address} icon={<MapPin className="h-3.5 w-3.5 text-ink-faint" aria-hidden="true" />} />
                    )}
                    {addressSpecific.map(k => (
                      <InfoRow key={k} field={k} label={prettyLabel(k, t)} value={p[k]} icon={<MapPin className="h-3.5 w-3.5 text-ink-faint" aria-hidden="true" />} />
                    ))}
                  </Section>

                  {/* Admission / Other Info */}
                  <Section title={t('student.admissionDetails')} icon={<Info className="h-3.5 w-3.5 text-brand-fg" aria-hidden="true" />}>
                    {admissionInfoFields.map(k => (
                      <InfoRow key={k} field={k} label={prettyLabel(k, t)} value={p[k]} />
                    ))}
                  </Section>

                </div>
              ) : (
                <div className="empty-state py-5">
                  <AlertCircle className="h-4 w-4" aria-hidden="true" />
                  <p className="t-support">{t('student.personalUnavailable')}</p>
                </div>
              )}
            </div>

            {/* ── Graduation Status ────────────────────────────────────────── */}
            {(grad.graduation_status || grad.graduation_year || grad.student_type) && (
              <div className="border-b border-line bg-ok-soft/60 px-4 py-3 sm:px-5">
                <h3 className="t-card mb-2 flex flex-wrap items-center gap-2 text-ink">
                  <GraduationCap className="h-4 w-4 text-ok" aria-hidden="true" />
                  {t('student.graduationStatus')}
                </h3>
                <div className="flex flex-wrap gap-x-6 gap-y-3">
                  {grad.student_type && (
                    <div className="min-w-0">
                      <p className="t-label text-ink-mute">{t('student.type')}</p>
                      <p className="t-body break-words font-semibold text-ink">{grad.student_type}</p>
                    </div>
                  )}
                  {grad.admission_batch && (
                    <div className="min-w-0">
                      <p className="t-label text-ink-mute">{t('student.admissionBatch')}</p>
                      <p className="t-body break-words font-semibold text-ink tabular-nums">{grad.admission_batch}</p>
                    </div>
                  )}
                  {grad.graduation_year && (
                    <div className="min-w-0">
                      <p className="t-label text-ink-mute">{t('student.graduationYear')}</p>
                      <p className="t-body break-words font-bold text-ok tabular-nums">{grad.graduation_year}</p>
                    </div>
                  )}
                  {grad.graduation_status && (
                    <div className="min-w-0">
                      <p className="t-label text-ink-mute">{t('common.status')}</p>
                      <GradBadge status={grad.graduation_status} />
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* ── Academic Information — SGPA / Marks ─────────────────────── */}
            <div className="border-b border-line p-4 sm:p-5">
              <h3 className="t-card mb-3 flex flex-wrap items-center gap-2 text-ink">
                <BookOpen className="h-4 w-4 text-brand-fg" aria-hidden="true" />
                {t('student.academicInfo')}
                {!hasAcademic && (
                  <span className="t-support ml-1 flex flex-wrap items-center gap-1 font-normal text-ink-mute">
                    <AlertCircle className="h-3.5 w-3.5" aria-hidden="true" />
                    {t('student.noAcademicShort')}
                  </span>
                )}
              </h3>
              {hasAcademic ? (
                <GpaTable data={student.academic_rows} />
              ) : (
                <div className="empty-state py-4">
                  <AlertCircle className="h-4 w-4" aria-hidden="true" />
                  <p className="t-support">{t('student.academicUnavailable')}</p>
                </div>
              )}
            </div>

            {/* ── Backlogs ─────────────────────────────────────────────────── */}
            <div className="border-b border-line p-4 sm:p-5">
              <h3 className="t-card mb-3 flex flex-wrap items-center gap-2 text-ink">
                <FileWarning className="h-4 w-4 text-warn" aria-hidden="true" />
                {t('student.backlogs')}
              </h3>
              <BacklogsSection usn={student.usn} rawText={backlogs_raw} />
            </div>

            {/* ── Fees ─────────────────────────────────────────────────────── */}
            <div className="p-4 sm:p-5">
              <h3 className="t-card mb-3 flex flex-wrap items-center gap-2 text-ink">
                <CreditCard className="h-4 w-4 text-brand-fg" aria-hidden="true" />
                {t('student.fees')}
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
          onSaved={() => { setNonce(n => n + 1); setFlashUsn(editor.usn); }}
        />
      )}
      {editor?.type === 'fees' && (
        <EditFeesModal
          usn={editor.usn}
          name={editor.name}
          onClose={() => setEditor(null)}
          onSaved={() => { setNonce(n => n + 1); setFlashUsn(editor.usn); }}
        />
      )}
    </div>
  );
}
