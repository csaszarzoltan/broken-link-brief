"""Application service for evidence-aware finding and verification workflows."""
from __future__ import annotations
from threading import Lock
from brokenlinkbrief.confidence import ProbeAttempt, classify_evidence
from brokenlinkbrief.triage import extract_occurrences

class FindingService:
    _active: set[str]=set(); _lock=Lock()
    def __init__(self, store): self.store=store
    def observe(self, project_id, occurrence, attempts: list[ProbeAttempt]):
        assessment=classify_evidence(attempts)
        return self.store.upsert(project_id,occurrence,assessment,attempts)
    def verify(self,finding_id,version,target_attempts,source_bodies):
        with self._lock:
            if finding_id in self._active: raise ValueError('FINDING_VERIFICATION_IN_PROGRESS')
            self._active.add(finding_id)
        try:
            detail=self.store.detail(finding_id); target=detail['target_url']; assessment=classify_evidence(target_attempts)
            checked=present=0; failures=[]
            for source,body in source_bodies.items():
                if body is None: failures.append({'source_url':source,'error':'fetch-failed'}); continue
                checked += 1
                if any(o.target_url==target for o in extract_occurrences(source,body)): present += 1
            if assessment.classification=='RECOVERED': outcome='RECOVERED'
            elif checked and not present and not failures: outcome='REMOVED_FROM_SOURCE'
            elif assessment.classification=='CONFIRMED_BROKEN' and present: outcome='STILL_BROKEN'
            else: outcome='INCONCLUSIVE'
            finding=self.store.record_verification(finding_id,version,outcome,checked,present,failures)
            return {'outcome':outcome,'finding':finding,'target_assessment':assessment.__dict__,'sources_checked':checked,'sources_present':present,'source_failures':failures}
        finally:
            with self._lock: self._active.discard(finding_id)
