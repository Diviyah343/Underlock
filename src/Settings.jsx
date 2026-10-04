import { useEffect, useState } from 'react'
import { Check } from 'lucide-react'

const STORAGE_KEY = 'underlock.user-settings'

const DEFAULT_RULES = [
  {
    id: 'amount-average',
    title: 'Flag transactions over 10x account average',
    description: 'Triggers when an outflow exceeds the 90-day moving average volume by 10x or greater.',
    enabled: true,
  },
  {
    id: 'new-beneficiary-high-amount',
    title: 'Flag new beneficiary + high amount within 1 hour',
    description: 'Triggers on wires exceeding $25,000 sent within 60 minutes of counterparty creation.',
    enabled: true,
  },
  {
    id: 'new-device-transfer',
    title: 'Flag login from new device + immediate transfer',
    description: 'Evaluates session fingerprint mismatch followed by transaction dispatch within 5 minutes.',
    enabled: true,
  },
  {
    id: 'multi-hop-transfer',
    title: 'Flag multi-hop rapid fund transfers',
    description: 'Identifies accounts receiving and forwarding equal sums across 3 or more nodes within 24 hours.',
    enabled: false,
  },
]

function makeDefaultSettings() {
  return {
    thresholds: { medium: 40, high: 75 },
    rules: DEFAULT_RULES.map((rule) => ({ ...rule })),
    notifications: { email: true, inApp: true, sms: false },
    lastSavedAt: 'Today at 09:14 UTC',
  }
}

function readSavedSettings() {
  if (typeof window === 'undefined') return makeDefaultSettings()
  try {
    const stored = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? 'null')
    if (!stored) return makeDefaultSettings()
    const defaults = makeDefaultSettings()
    return {
      ...defaults,
      ...stored,
      thresholds: { ...defaults.thresholds, ...stored.thresholds },
      rules: Array.isArray(stored.rules) ? stored.rules : defaults.rules,
      notifications: { ...defaults.notifications, ...stored.notifications },
    }
  } catch {
    return makeDefaultSettings()
  }
}

function validateThresholds(thresholds) {
  const errors = {}
  const medium = Number(thresholds.medium)
  const high = Number(thresholds.high)

  if (!Number.isInteger(medium) || medium < 1 || medium > 100) {
    errors.medium = 'Enter a whole number from 1 to 100.'
  }
  if (!Number.isInteger(high) || high < 0 || high > 100) {
    errors.high = 'Enter a whole number from 0 to 100.'
  }
  if (!errors.medium && !errors.high && medium >= high) {
    errors.high = 'High risk must be greater than the medium threshold.'
  }
  return errors
}

export function useSettings(onDirtyChange) {
  const [initialSettings] = useState(readSavedSettings)
  const [savedSettings, setSavedSettings] = useState(initialSettings)
  const [draftSettings, setDraftSettings] = useState(initialSettings)
  const validationErrors = validateThresholds(draftSettings.thresholds)
  const dirty = JSON.stringify({ ...draftSettings, lastSavedAt: null })
    !== JSON.stringify({ ...savedSettings, lastSavedAt: null })

  useEffect(() => {
    onDirtyChange?.(dirty)
  }, [dirty, onDirtyChange])

  function updateThreshold(field, value) {
    setDraftSettings((current) => ({
      ...current,
      thresholds: { ...current.thresholds, [field]: value === '' ? '' : Number(value) },
    }))
  }

  function updateRule(ruleId, enabled) {
    setDraftSettings((current) => ({
      ...current,
      rules: current.rules.map((rule) => rule.id === ruleId ? { ...rule, enabled } : rule),
    }))
  }

  function updateNotification(channel, enabled) {
    setDraftSettings((current) => ({
      ...current,
      notifications: { ...current.notifications, [channel]: enabled },
    }))
  }

  function save() {
    if (Object.keys(validationErrors).length) return false
    // TODO: replace local persistence with the settings API after aligning its defaults and account model.
    const nextSettings = { ...draftSettings, lastSavedAt: new Date().toISOString() }
    setSavedSettings(nextSettings)
    setDraftSettings(nextSettings)
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(nextSettings))
    } catch {
      // Keep the saved settings in memory if browser storage is unavailable.
    }
    return true
  }

  function reset() {
    if (!window.confirm('Reset all settings to their defaults?')) return false
    setDraftSettings(makeDefaultSettings())
    return true
  }

  return {
    savedSettings,
    draftSettings,
    dirty,
    validationErrors,
    updateThreshold,
    updateRule,
    updateNotification,
    save,
    reset,
  }
}

function SettingsSection({ title, description, children, className = '' }) {
  return (
    <section className={`settings-section ${className}`}>
      <header className="settings-section-header">
        <h2>{title}</h2>
        {description && <p>{description}</p>}
      </header>
      {children}
    </section>
  )
}

function ThresholdRow({ label, tone, value, onChange, readOnly, error, inputLabel }) {
  return (
    <div className={`settings-threshold-row ${error ? 'has-error' : ''}`}>
      <div className="settings-row-label">
        <span className={`settings-risk-dot settings-risk-dot-${tone}`} aria-hidden="true" />
        <span>{label}</span>
      </div>
      {readOnly ? (
        <output className="settings-number-display" aria-label={inputLabel}>{value}</output>
      ) : (
        <input
          className="settings-number-input"
          type="number"
          min="0"
          max="100"
          step="1"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          aria-label={inputLabel}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? `${inputLabel}-error` : undefined}
        />
      )}
      {error && <p className="settings-field-error" id={`${inputLabel}-error`}>{error}</p>}
    </div>
  )
}

function RuleToggleRow({ rule, onChange }) {
  return (
    <div className="settings-rule-row">
      <div className="settings-rule-copy">
        <h3>{rule.title}</h3>
        <p>{rule.description}</p>
      </div>
      <button
        className={`settings-switch ${rule.enabled ? 'is-on' : ''}`}
        type="button"
        role="switch"
        aria-checked={rule.enabled}
        aria-label={rule.title}
        onClick={() => onChange(rule.id, !rule.enabled)}
      >
        <span />
      </button>
    </div>
  )
}

function NotificationCheckbox({ id, label, description, checked, onChange }) {
  return (
    <label className="settings-notification-row" htmlFor={`notification-${id}`}>
      <span className="settings-checkbox-wrap">
        <input
          id={`notification-${id}`}
          type="checkbox"
          checked={checked}
          onChange={(event) => onChange(id, event.target.checked)}
        />
        {checked && <Check className="settings-checkbox-check" size={18} strokeWidth={3} aria-hidden="true" />}
      </span>
      <span className="settings-notification-copy">
        <strong>{label}</strong>
        <span>{description}</span>
      </span>
    </label>
  )
}

function AccountRows({ currentUser, onSignOut }) {
  const rows = [
    ['Analyst name', currentUser.name, 'account-value-name'],
    ['Analyst ID', currentUser.id, 'account-value-id'],
    ['Role', currentUser.role, 'account-value-name'],
    ['Session status', currentUser.sessionStatus, 'account-value-session'],
  ]

  return (
    <SettingsSection title="Account" className="settings-account-section">
      <dl className="settings-account-rows">
        {rows.map(([label, value, valueClass]) => (
          <div className="settings-account-row" key={label}>
            <dt>{label}</dt>
            <dd className={valueClass}>{value}</dd>
          </div>
        ))}
      </dl>
      <button className="settings-sign-out" type="button" onClick={onSignOut}>Sign out</button>
    </SettingsSection>
  )
}

function formatLastSaved(value) {
  if (value === 'Today at 09:14 UTC') return value
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Today at 09:14 UTC'
  return `Today at ${new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(date)} UTC`
}

function SettingsFooter({ dirty, invalid, lastSavedAt, savedNotice, onSave, onReset }) {
  return (
    <footer className="settings-footer">
      <div className="settings-footer-actions">
        <button className="settings-save-button" type="button" disabled={!dirty || invalid} onClick={onSave}>Save changes</button>
        <button className="settings-reset-button" type="button" onClick={onReset}>Reset to defaults</button>
        {savedNotice && <span className="settings-saved-notice" role="status">Saved</span>}
      </div>
      <p>Last saved: {formatLastSaved(lastSavedAt)}</p>
    </footer>
  )
}

export default function SettingsPage({ currentUser, onDirtyChange, onSignOut }) {
  const {
    savedSettings,
    draftSettings,
    dirty,
    validationErrors,
    updateThreshold,
    updateRule,
    updateNotification,
    save,
    reset,
  } = useSettings(onDirtyChange)
  const [savedNotice, setSavedNotice] = useState(false)
  const invalid = Object.keys(validationErrors).length > 0
  const medium = Number(draftSettings.thresholds.medium)
  const lowRange = Number.isInteger(medium) && medium > 0 ? `0 - ${medium - 1}` : '0 - --'

  function handleSave() {
    if (save()) {
      setSavedNotice(true)
      window.setTimeout(() => setSavedNotice(false), 2200)
    }
  }

  return (
    <main className="settings-page">
      <h1>Settings</h1>
      <div className="settings-sections">
        <SettingsSection title="Risk tier thresholds" description="Configure score cutoffs for alert severity classification.">
          <div className="settings-threshold-rows">
            <ThresholdRow label="Low risk range" tone="low" value={lowRange} readOnly inputLabel="Low risk range" />
            <ThresholdRow label="Medium risk starts at score" tone="medium" value={draftSettings.thresholds.medium} onChange={(value) => updateThreshold('medium', value)} error={validationErrors.medium} inputLabel="Medium risk starts at score" />
            <ThresholdRow label="High risk starts at score" tone="high" value={draftSettings.thresholds.high} onChange={(value) => updateThreshold('high', value)} error={validationErrors.high} inputLabel="High risk starts at score" />
          </div>
        </SettingsSection>

        <SettingsSection title="Alert rules" description="Automated trigger rules evaluated against incoming transaction events.">
          <div className="settings-rule-rows">
            {draftSettings.rules.map((rule) => <RuleToggleRow key={rule.id} rule={rule} onChange={updateRule} />)}
          </div>
        </SettingsSection>

        <SettingsSection title="Notifications" description="Delivery channels for high-risk alert dispatch and urgent case escalation.">
          <div className="settings-notification-rows">
            <NotificationCheckbox id="email" label="Email" description="Send digest and critical alerts to analyst email (an-8902@security.underlock.bank)" checked={draftSettings.notifications.email} onChange={updateNotification} />
            <NotificationCheckbox id="inApp" label="In-app" description="Display desktop banner notifications and audio cue on incoming high-risk alerts" checked={draftSettings.notifications.inApp} onChange={updateNotification} />
            <NotificationCheckbox id="sms" label="SMS" description="Send SMS ping to verified workstation mobile device on critical escalation" checked={draftSettings.notifications.sms} onChange={updateNotification} />
          </div>
        </SettingsSection>

        <AccountRows currentUser={currentUser} onSignOut={onSignOut} />
      </div>
      <SettingsFooter
        dirty={dirty}
        invalid={invalid}
        lastSavedAt={savedSettings.lastSavedAt}
        savedNotice={savedNotice}
        onSave={handleSave}
        onReset={reset}
      />
    </main>
  )
}