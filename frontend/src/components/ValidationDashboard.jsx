/**
 * ValidationDashboard — Data quality checks: missing values, invalid SGPA, duplicates.
 */
import { useState, useEffect } from 'react';
import api from '../services/api';
import { getUserMessage } from '../services/errors';
import { useI18n } from '../context/LanguageContext';
import CountUp from './CountUp';
import { AlertTriangle, CheckCircle, RefreshCw, Users } from 'lucide-react';

// Keys are backend issue-type values — they must never be renamed or translated.
// Only the class they resolve to changed (stock palette → design tokens).
const ISSUE_COLORS = {
  missing_name:       'badge-warn',
  invalid_sgpa:       'badge-err',
  invalid_semester:   'badge-err',
  too_many_semesters: 'badge-info',
};

// Same reason: the display label is frontend-owned, the raw value is the fallback.
const ISSUE_LABELS = {
  missing_name:       'validation.typeMissingName',
  invalid_sgpa:       'validation.typeInvalidSgpa',
  invalid_semester:   'validation.typeInvalidSemester',
  too_many_semesters: 'validation.typeTooManySemesters',
};

export default function ValidationDashboard() {
  const { t } = useI18n();
  const [data, setData]         = useState(null);
  const [dupes, setDupes]       = useState([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState('');

  const load = async () => {
    setLoading(true); setError('');
    try {
      const [v, d] = await Promise.all([
        api.get('/files/validation'),
        api.get('/files/duplicates'),
      ]);
      setData(v.data);
      setDupes(d.data);
    } catch (e) {
      setError(getUserMessage(e, t('validation.errLoad')));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  if (loading) return (
    <div role="status" aria-live="polite" className="card overflow-hidden">
      <div className="fetch-bar" aria-hidden="true" />
      <div className="flex items-center justify-center gap-2 py-12 text-ink-mute t-body">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-line border-t-brand" aria-hidden="true" />
        {t('validation.loading')}
      </div>
      <div className="skeleton-list px-5 pb-5" aria-hidden="true">
        <span className="skeleton w-full" />
        <span className="skeleton w-11/12" />
        <span className="skeleton w-3/4" />
      </div>
    </div>
  );

  if (error) return (
    <div className="flex items-start gap-2 rounded-lg border border-err/25 bg-err-soft p-4 text-err t-body">
      <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" />
      <span className="min-w-0 break-words">{error}</span>
    </div>
  );

  return (
    <div className="anim-fade-up space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="t-section text-ink">{t('validation.title')}</h2>
        <button
          onClick={load}
          className="btn btn-sm btn-ghost px-2"
          title={t('common.refresh')}
          aria-label={t('common.refresh')}
        >
          <RefreshCw className="h-3.5 w-3.5 text-ink-mute" />
        </button>
      </div>

      {/* Summary */}
      {data && (
        <div className="stagger grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div className="card card-interactive lift relative p-4 text-center">
            <p className="t-value text-ink"><CountUp value={data.total_students} /></p>
            <p className="t-support mt-1 text-ink-mute">{t('validation.totalStudents')}</p>
            <span className="sheen" aria-hidden="true" />
          </div>
          <div className="card card-interactive lift relative p-4 text-center">
            <p className="t-value text-ink"><CountUp value={data.total_marks} /></p>
            <p className="t-support mt-1 text-ink-mute">{t('validation.markRecords')}</p>
            <span className="sheen" aria-hidden="true" />
          </div>
          <div className={`card-interactive lift relative rounded-lg border p-4 text-center ${data.issue_count === 0 ? 'border-ok/25 bg-ok-soft' : 'border-err/25 bg-err-soft'}`}>
            <p className={`t-value ${data.issue_count === 0 ? 'text-ok' : 'text-err'}`}><CountUp value={data.issue_count} /></p>
            <p className={`t-support mt-1 ${data.issue_count === 0 ? 'text-ok' : 'text-err'}`}>{t('validation.issuesFound')}</p>
            <span className="sheen" aria-hidden="true" />
          </div>
        </div>
      )}

      {/* All clear */}
      {data?.issue_count === 0 && (
        <div className="flex items-start gap-3 rounded-lg border border-ok/25 bg-ok-soft p-4 text-ok">
          <CheckCircle className="mt-0.5 h-5 w-5 flex-shrink-0" />
          <span className="t-body font-medium">{t('validation.allClean')}</span>
        </div>
      )}

      {/* Issues list */}
      {data?.issues?.length > 0 && (
        <div className="table-wrap">
          <div className="flex items-center gap-2 border-b border-err/20 bg-err-soft px-4 py-3 text-err">
            <AlertTriangle className="h-4 w-4 flex-shrink-0" />
            <span className="t-card">{t('validation.issueCount', { n: data.issues.length })}</span>
          </div>
          <div className="table-scroll max-h-96 overflow-y-auto">
            <table className="w-full t-table">
              <thead>
                <tr>
                  <th scope="col" className="th">{t('validation.colIssue')}</th>
                  <th scope="col" className="th">{t('validation.colUsn')}</th>
                  <th scope="col" className="th">{t('validation.colSemester')}</th>
                  <th scope="col" className="th">{t('validation.colDetail')}</th>
                </tr>
              </thead>
              <tbody>
                {data.issues.map((issue, i) => (
                  <tr key={i} className="tr-hover align-top">
                    <td className="td">
                      <span className={`badge ${ISSUE_COLORS[issue.type] || 'badge-quiet'}`}>
                        {ISSUE_LABELS[issue.type] ? t(ISSUE_LABELS[issue.type]) : issue.type.replace(/_/g, ' ')}
                      </span>
                    </td>
                    <td className="td">
                      {issue.usn
                        ? <span className="font-mono whitespace-nowrap text-ink" title={issue.usn}>{issue.usn}</span>
                        : <span className="text-ink-faint">—</span>}
                    </td>
                    <td className="td whitespace-nowrap">
                      {issue.semester ? t('validation.semester', { n: issue.semester }) : <span className="text-ink-faint">—</span>}
                    </td>
                    <td className="td text-ink-soft">{issue.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Duplicates */}
      {dupes.length > 0 && (
        <div className="table-wrap">
          <div className="flex items-center gap-2 border-b border-line bg-sunken px-4 py-3">
            <Users className="h-4 w-4 text-brand-fg" />
            <span className="t-card text-ink">{t('validation.duplicatesTitle', { n: dupes.length })}</span>
          </div>
          <div className="table-scroll">
            <table className="w-full t-table">
              <thead>
                <tr>
                  <th scope="col" className="th">{t('validation.colName')}</th>
                  <th scope="col" className="th text-right">{t('validation.colRecords')}</th>
                  <th scope="col" className="th">{t('validation.colUsns')}</th>
                </tr>
              </thead>
              <tbody>
                {dupes.map((d, i) => (
                  <tr key={i} className="tr-hover">
                    <td className="td font-medium text-ink" title={d.name}>{d.name}</td>
                    <td className="td text-right whitespace-nowrap text-brand-fg font-semibold">{t('validation.recordCount', { n: d.cnt })}</td>
                    <td className="td font-mono whitespace-nowrap text-ink-mute" title={d.usns}>{d.usns}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
