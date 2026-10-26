import React from "react";
import { CheckCircle, Minus, Info } from "lucide-react";
import { UI_COLORS as C } from "../../styles/uiTokens";

const CARD = {
  background: C.surface,
  borderRadius: '10px',
  border: `1px solid ${C.border}`,
  boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
  padding: '20px 24px',
  marginBottom: '14px',
  width: '100%',
  boxSizing: 'border-box',
  minWidth: 0,
};

const TH = {
  textAlign: 'left',
  padding: '9px 12px',
  borderBottom: `2px solid ${C.primary}`,
  color: C.primaryText,
  fontWeight: 700,
  fontSize: '11px',
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
};

const TD = {
  padding: '8px 12px',
  borderBottom: `1px solid ${C.border}`,
  verticalAlign: 'top',
  fontSize: '13px',
  color: C.textPrimary,
};

const TABLE = { width: '100%', borderCollapse: 'collapse', fontSize: '13px' };

const Badge = ({ color = C.primary, children }) => (
  <span style={{
    display: 'inline-block', padding: '2px 9px', borderRadius: '10px',
    fontSize: '11px', fontWeight: 600, background: color, color: '#fff',
    marginRight: '5px',
  }}>{children}</span>
);

const ScoreBar = ({ score, max = 100 }) => {
  if(typeof score!=='number'||!Number.isFinite(score))return <span>Impact score not recorded</span>;
  const pct = Math.max(0, Math.min((score / max) * 100, 100));
  const barColor = C.primary;
  const label = 'Evidence indicator; severity not assessed';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
      <div style={{ flex: 1, height: '8px', background: C.border, borderRadius: '4px', overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: barColor, borderRadius: '4px', transition: 'width .4s ease' }} />
      </div>
      <span style={{ fontSize: '12px', fontWeight: 700, color: barColor, minWidth: '100px', whiteSpace: 'nowrap' }}>
        {score} · {label}
      </span>
    </div>
  );
};

const SimilarityBar = ({ score }) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
    <div style={{ width: '80px', height: '6px', background: C.border, borderRadius: '3px', overflow: 'hidden' }}>
      <div style={{ width: `${Math.min(score, 100)}%`, height: '100%', background: C.primary, borderRadius: '3px' }} />
    </div>
    <span style={{ fontSize: '12px', fontWeight: 600, color: C.textSec }}>{score}</span>
  </div>
);

const SectionHeader = ({ icon: Icon, label, count, color = C.primary }) => (
  <div style={{
    fontSize: '12px', fontWeight: 700, color: C.textPrimary, marginBottom: '12px',
    marginTop: '20px', display: 'flex', alignItems: 'center', gap: '8px',
    textTransform: 'uppercase', letterSpacing: '0.05em',
  }}>
    <Icon size={11} color={color} strokeWidth={2.2} />
    <span>{label}</span>
    {count !== undefined && (
      <span style={{
        background: C.primaryLight, color: C.primaryText,
        fontSize: '11px', fontWeight: 700, padding: '1px 8px', borderRadius: '10px',
      }}>{count}</span>
    )}
  </div>
);

const ResultEmptyState = ({
  icon: Icon = Info,
  title = 'No result details available',
  message = 'The service returned successfully, but there is no structured recommendation content to display yet.',
  color = C.textSec,
}) => (
  <div style={{ ...CARD, textAlign: 'center', padding: '30px' }}>
    <Icon size={24} color={color} style={{ display: 'block', margin: '0 auto 10px' }} />
    <div style={{ fontWeight: 700, color: C.textPrimary, marginBottom: '6px' }}>{title}</div>
    <div style={{ color: C.textSec, lineHeight: 1.6 }}>{message}</div>
  </div>
);

const CheckCell = ({ value }) => value
  ? <CheckCircle size={14} color={C.green} strokeWidth={2.5} />
  : <Minus size={13} color={C.textMuted} />;

const ResultTabBar = ({ tabs, active, onChange }) => (
  <div style={{
    display: 'flex', gap: 0, borderBottom: `1px solid ${C.border}`,
    background: C.surface, marginBottom: '14px', flexWrap: 'wrap',
    borderRadius: '8px 8px 0 0', padding: '0 4px',
    boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
  }}>
    {tabs.map(t => {
      const isActive = active === t.id;
      const col = t.color || C.primary;
      return (
        <button key={t.id} onClick={() => onChange(t.id)} style={{
          display: 'inline-flex', alignItems: 'center', gap: '5px',
          padding: '9px 14px', border: 'none', background: 'transparent',
          borderBottom: isActive ? `2px solid ${col}` : '2px solid transparent',
          color: isActive ? col : C.textSec,
          fontSize: '12px', fontWeight: isActive ? 700 : 500,
          cursor: 'pointer', transition: 'all .12s', marginBottom: '-1px',
          whiteSpace: 'nowrap',
        }}>
          {t.label}
          {t.count !== undefined && (
            <span style={{
              background: isActive ? col : C.border,
              color: isActive ? '#fff' : C.textSec,
              fontSize: '10px', fontWeight: 700,
              padding: '1px 6px', borderRadius: '10px', minWidth: '18px', textAlign: 'center',
            }}>{t.count}</span>
          )}
        </button>
      );
    })}
  </div>
);

const MetricChip = ({ value, label, color }) => (
  <div style={{
    display: 'inline-flex', flexDirection: 'column', alignItems: 'center',
    padding: '8px 16px', borderRadius: '8px',
    background: 'rgba(255,255,255,0.7)', border: `1px solid color-mix(in srgb, ${color} 30%, transparent)`,
    minWidth: '72px',
  }}>
    <span style={{ fontSize: '20px', fontWeight: 800, color, lineHeight: 1 }}>{value}</span>
    <span style={{ fontSize: '10px', fontWeight: 600, color: C.textSec, textTransform: 'uppercase', letterSpacing: '0.04em', marginTop: '3px' }}>{label}</span>
  </div>
);

export { CARD, TH, TD, TABLE, Badge, ScoreBar, SimilarityBar, SectionHeader, ResultEmptyState, CheckCell, ResultTabBar, MetricChip };
