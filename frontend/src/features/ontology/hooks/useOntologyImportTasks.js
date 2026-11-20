import { useEffect, useState, useRef } from 'react';
import { API_METHODS } from '../../../services/apiClient';
import { apiErrorMessage } from '../../../utils/apiErrorMessage';

// The registry request belongs to this workspace, not to its selected row.
// Status/preview reads belong to the selected task and are cancelled together.
export default function useOntologyImportTasks() {
  const [importTasks, setImportTasks] = useState([]);
  const requestedTask = useRef(new URLSearchParams(window.location.hash.split('?')[1] || '').get('import_task_id') || '');
  const [selectedImportTaskId, setSelectedImportTaskId] = useState(requestedTask.current);
  const [importTasksLoading, setLoading] = useState(false);
  const [importTasksError, setError] = useState(null);
  const [revision, setRevision] = useState(0);
  const [selection, setSelection] = useState(null);

  const taskList = useRef(importTasks);
  taskList.current = importTasks;
  const registryLoaded = useRef(false);
  useEffect(() => {
    const applyRoute = () => {
      const id = new URLSearchParams(window.location.hash.split('?')[1] || '').get('import_task_id') || '';
      if (id === requestedTask.current) return;
      requestedTask.current = id;
      setSelection(null);
      const missing = id && registryLoaded.current && !taskList.current.some(task => task.task_id === id);
      setError(missing ? 'The linked import is unavailable in this connection. No different source was selected.' : null);
      setSelectedImportTaskId(missing ? '' : id);
    };
    window.addEventListener('hashchange', applyRoute);
    window.addEventListener('popstate', applyRoute);
    return () => { window.removeEventListener('hashchange', applyRoute); window.removeEventListener('popstate', applyRoute); };
  }, []);
  const selectTask = id => {
    requestedTask.current = id;
    const [path, query=''] = window.location.hash.split('?');
    const params = new URLSearchParams(query);
    if (id) params.set('import_task_id', id); else params.delete('import_task_id');
    window.history.replaceState(null, '', path + (params.size ? '?' + params.toString() : ''));
    setError(null);
    setSelectedImportTaskId(id);
  };

  useEffect(() => {
    const refresh = () => setRevision(value => value + 1);
    const reset = () => {
      registryLoaded.current = false;
      setImportTasks([]);
      setSelectedImportTaskId('');
      setSelection(null);
      setError(null);
      refresh();
    };
    const sessions = ['depo:credentials-changed', 'depo:credentials-cleared', 'depo:session-expired','depo:session-replaced', 'dt-schema-cleaned'];
    sessions.forEach(event => window.addEventListener(event, reset));
    window.addEventListener('depo:page-task-updated', refresh);
    return () => {
      sessions.forEach(event => window.removeEventListener(event, reset));
      window.removeEventListener('depo:page-task-updated', refresh);
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    API_METHODS.import.getTasks({ signal: controller.signal }).then(response => {
      if (controller.signal.aborted) return;
      const tasks = response.data?.tasks;
      if(!Array.isArray(tasks)||tasks.some(task=>!task||typeof task.task_id!=='string'))throw new Error('Import task registry returned an invalid response. Refresh after checking the ingestion service.');
      registryLoaded.current = true;
      setImportTasks(tasks);
      const requested = requestedTask.current;
      if (requested && !tasks.some(task => task.task_id === requested)) setError('The linked import is unavailable in this connection. No different source was selected.');
      setSelectedImportTaskId(current => requested ? (tasks.some(task => task.task_id === requested) ? requested : '') : tasks.some(task => task.task_id === current) ? current : tasks[0]?.task_id || '');
    }).catch(failure => {
      if (!controller.signal.aborted) setError(apiErrorMessage(failure, 'Failed to load instance tasks.'));
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [revision]);

  useEffect(() => {
    if (!selectedImportTaskId) return;
    const controller = new AbortController();
    Promise.allSettled([
      API_METHODS.import.getStatus(selectedImportTaskId, { signal: controller.signal }),
      API_METHODS.import.getPreview(selectedImportTaskId, { signal: controller.signal }),
    ]).then(([status, preview]) => {
      if (controller.signal.aborted) return;
      setSelection({
        taskId: selectedImportTaskId,
        revision,
        details: status.status === 'fulfilled' ? status.value?.data || null : null,
        preview: preview.status === 'fulfilled' ? preview.value?.data || null : null,
        detailsError: status.status === 'rejected' ? apiErrorMessage(status.reason, 'Import status is unavailable.') : null,
        previewError: preview.status === 'rejected' ? apiErrorMessage(preview.reason, 'Import preview is unavailable.') : null,
      });
    });
    return () => controller.abort();
  }, [selectedImportTaskId, revision]);

  // Hide previous evidence during the render that changes selection, before effects run.
  const current = selection?.taskId === selectedImportTaskId && selection?.revision === revision ? selection : null;
  return {
    importTasks, selectedImportTaskId, setSelectedImportTaskId: selectTask,
    importTasksLoading, importTasksError,
    refreshImportTasks: () => setRevision(value => value + 1),
    selectedImportTaskDetails: current?.details || null,
    selectedImportTaskPreview: current?.preview || null,
    selectedImportTaskLoading: Boolean(selectedImportTaskId && !current),
    selectedImportTaskError: [importTasksError, current?.detailsError, current?.previewError].filter(Boolean).join(' '),
  };
}
