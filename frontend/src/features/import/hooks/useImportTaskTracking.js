import { useCallback, useEffect } from 'react';
import usePollerRegistry from '../../../hooks/usePollerRegistry';
import { apiClient } from '../../../services/apiClient';
import { buildUrl, replaceParams, API } from '../../../config';
import { backendToFrontendStage } from '../../../workflows/workflowEngine';
import { isAwaitingImportApproval } from '../../../workflows/importPresentation';

export default function useImportTaskTracking({ isMountedRef, setPipelineStatus, setPreviewsByTask }) {
  const { activePollersRef, clearPoller, clearAllPollers, schedulePoller } = usePollerRegistry(isMountedRef);
  const pollPipelineProgress = useCallback(async (taskId, fileId) => {
    const pollerKey = `${taskId}:${fileId}`;
    if (activePollersRef.current.has(pollerKey)) {
      return;
    }
    activePollersRef.current.add(pollerKey);
    const maxAttempts = 600;
    let attempts = 0;

    const poll = async (signal) => {
      try {
        if (signal?.aborted || !activePollersRef.current.has(pollerKey) || !isMountedRef.current) {
          return;
        }
        const statusUrl = buildUrl(replaceParams(API.import.status, { task_id: taskId }));
        const res = await apiClient.get(statusUrl, { signal });
        if (signal?.aborted || !activePollersRef.current.has(pollerKey) || !isMountedRef.current) {
          return;
        }
        const data = res.data;

        // Task creation is async in backend; treat not_found as transient instead of hard failure.
        if (data?.status === 'not_found') {
          if (attempts < maxAttempts) {
            attempts++;
            setPipelineStatus(prev => ({
              ...prev,
              [fileId]: {
                ...(prev[fileId] || {}),
                taskId,
                stage: 'upload',
                progress: 5,
                status: 'processing',
                message: 'Initializing task...',
                lastUpdatedAt: new Date().toISOString()
              }
            }));
            schedulePoller(pollerKey, poll, 2000);
          } else {
            clearPoller(pollerKey);
            setPipelineStatus(previous => ({ ...previous, [fileId]: {
              ...(previous[fileId] || {}), taskId, resumeExpired: true,
              message: 'Task status is still unavailable. The task is retained; check status again before retrying submission.',
            } }));
          }
          return;
        }

        const mappedStage = backendToFrontendStage[data.current_stage] || data.current_stage || 'upload';

        // F-NEW-8: normalize stats - backend parsers use different key names for entity/rel counts.
        const rawStats = data.stats || {};
        const entities_found =
          data.result?.nodes_created ??
          rawStats.entities_found ??
          rawStats.row_count ??
          rawStats.total_items ??
          rawStats.element_count;
        const relationships_found =
          data.result?.relationships_created ??
          rawStats.relationships_found ??
          rawStats.relationship_count;
        const normalizedStats = {
          ...rawStats,
          entities_found,
          relationships_found,
        };

        const shaclConforms = data?.result?.shacl_conforms ?? data?.shacl_conforms ?? null;
        const shaclFile = data?._shacl_file ?? data?.result?._shacl_file ?? null;

        setPipelineStatus(prev => {
          const previousStatus = prev[fileId] || {};
          const nextStatus = {
            ...previousStatus,
            taskId,
            stage: mappedStage,
            backendStage: data.current_stage,
            progress: data.progress,
            message: isAwaitingImportApproval(data) ? 'Parsing complete. Review the preview, then choose Load to knowledge graph and enter an approver.' : data.message,
            stats: normalizedStats,
            status: data.status,
            committing: typeof data.committing === 'boolean'
              ? data.committing
              : ((data.current_stage === 'ingest' || !!data.commit_phase) && data.status !== 'completed' && data.status !== 'failed'),
            error: data.error ? true : false,
            completedAt: data.status === 'completed' ? (previousStatus.completedAt || new Date().toLocaleTimeString()) : null,
            completedAtIso: data.status === 'completed' ? (previousStatus.completedAtIso || new Date().toISOString()) : null,
            lastUpdatedAt: new Date().toISOString(),
            commitPhase: data.commit_phase || null,
            // A previous commit attempt may have failed in this browser state.
            // The backend's ready_for_commit state is authoritative: the preview
            // is valid and a new commit may be started, so do not retain the old
            // retry banner after polling resumes or the task is restored.
            commitError: data.status === 'ready_for_commit' || data.status === 'completed'
              ? null
              : (data.commit_phase === 'error' ? (data.error || 'Commit failed') : null),
            batchProgress: data.batch_progress || null,
            commitMetrics: data.commit_metrics || null,
            shaclConforms,
            shaclFile,
            artifact_manifest: data.artifact_manifest,
            workflow_id: data.workflow_id,
            resumeExpired: false,
          };
          const previousComparable = { ...previousStatus };
          const nextComparable = { ...nextStatus };
          delete previousComparable.lastUpdatedAt;
          delete nextComparable.lastUpdatedAt;
          if (JSON.stringify(previousComparable) === JSON.stringify(nextComparable)) return prev;
          return { ...prev, [fileId]: nextStatus };
        });

        // Auto-set preview data when preview/verify stage or completed is reached
        if (data.current_stage === 'preview' || data.current_stage === 'verify' || data.status === 'completed') {
          const statusPreview = {
            ...data,
            row_count: normalizedStats.row_count ?? normalizedStats.entities_found ?? 0,
            columns: normalizedStats.columns || [],
            sample_rows: [],
            auto_schema: data.auto_schema || {},
          };
          setPreviewsByTask(prev => ({ ...prev, [taskId]: statusPreview }));
          // Fetch actual preview rows from the preview endpoint
          try {
            const previewUrl = buildUrl(replaceParams(API.import.preview, { task_id: taskId }));
            const previewRes = await apiClient.get(previewUrl, { signal });
            if (signal?.aborted || !activePollersRef.current.has(pollerKey) || !isMountedRef.current) {
              return;
            }
            if (previewRes.data) {
              // F2 FIX: spread preview endpoint fields directly onto previewData so the
              // modal can read row_count / columns / sample_rows / auto_schema at the top level.
              // Previously they were nested under .preview which the modal never read.
              setPreviewsByTask(previews => ({ ...previews, [taskId]: {
                ...previews[taskId],
                row_count:   previewRes.data.row_count   ?? previews[taskId]?.row_count   ?? 0,
                columns:     previewRes.data.columns     || previews[taskId]?.columns     || [],
                sample_rows: previewRes.data.sample_rows || previews[taskId]?.sample_rows || [],
                auto_schema: previewRes.data.auto_schema || previews[taskId]?.auto_schema || {},
              }}));
            }
          } catch (_) { /* preview is optional - continue without it */ }
        }

        // Optional preview failures include cancellation. Recheck ownership before
        // clearing/scheduling: a new poller may already own the same task key.
        if (signal?.aborted || !activePollersRef.current.has(pollerKey) || !isMountedRef.current) return;

        // Preview is a stable user decision point. Stop polling until the
        // user explicitly starts the knowledge graph commit, which starts a new poller.
        if ((data.status === 'ready_for_commit' && !data.committing && data.current_stage !== 'ingest') || data.status === 'completed' || data.status === 'failed') {
          clearPoller(pollerKey);
          return;
        }

        if (attempts < maxAttempts) {
          attempts++;
          const nextDelay =
            data.current_stage === 'ingest' || data.commit_phase
              ? 1500
              : 2500;
          schedulePoller(pollerKey, poll, nextDelay);
        } else {
          clearPoller(pollerKey);
        }
      } catch (err) {
        if (signal?.aborted || err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError' || err?.name === 'AbortError') {
          // A superseded read must not clear a new poller with the same task key.
          return;
        }
        if (attempts < maxAttempts) {
          attempts++;
          setPipelineStatus(prev => ({
            ...prev,
            [fileId]: {
              ...(prev[fileId] || {}),
              taskId,
              message: `Waiting for service response... ${err.message}`,
              lastUpdatedAt: new Date().toISOString(),
            }
          }));
          schedulePoller(pollerKey, poll, 3000);
          return;
        }
        clearPoller(pollerKey);
        setPipelineStatus(prev => ({
          ...prev,
          [fileId]: { ...prev[fileId], stage: 'error', message: err.message, error: true }
        }));
      }
    };

    // Initial and subsequent reads share the same per-task cancellation owner.
    schedulePoller(pollerKey, poll, 0);
  }, [activePollersRef, clearPoller, isMountedRef, schedulePoller]);
  useEffect(() => {
    const events = ['dt-schema-cleaned', 'depo:credentials-changed', 'depo:credentials-cleared', 'depo:session-expired'];
    events.forEach(event => window.addEventListener(event, clearAllPollers));
    return () => events.forEach(event => window.removeEventListener(event, clearAllPollers));
  }, [clearAllPollers]);
  return { pollPipelineProgress, clearPoller };
}
