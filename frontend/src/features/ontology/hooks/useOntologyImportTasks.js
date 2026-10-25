import { useEffect, useState } from 'react';
import { API_METHODS } from '../../../services/apiClient';
import { apiErrorMessage } from '../../../utils/apiErrorMessage';

// The registry request belongs to this workspace, not to its selected row.
// Status/preview reads belong to the selected task and are cancelled together.
export default function useOntologyImportTasks() {
  const [importTasks, setImportTasks] = useState([]);
  const [selectedImportTaskId, setSelectedImportTaskId] = useState('');
  const [importTasksLoading, setLoading] = useState(false);
  const [importTasksError, setError] = useState(null);
  const [revision, setRevision] = useState(0);
  const [selection, setSelection] = useState(null);

  useEffect(() => {
    const refresh = () => setRevision(value => value + 1);
    const reset = () => {
      setImportTasks([]);
      setSelectedImportTaskId('');
      setSelection(null);
      setError(null);
      refresh();
    };
    const sessions = ['depo:credentials-changed', 'depo:credentials-cleared', 'depo:session-expired', 'dt-schema-cleaned'];
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
      const tasks = response.data?.tasks || [];
      setImportTasks(tasks);
      setSelectedImportTaskId(current => current || tasks[0]?.task_id || '');
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
      });
    });
    return () => controller.abort();
  }, [selectedImportTaskId, revision]);

  // Hide previous evidence during the render that changes selection, before effects run.
  const current = selection?.taskId === selectedImportTaskId && selection?.revision === revision ? selection : null;
  return {
    importTasks, selectedImportTaskId, setSelectedImportTaskId,
    importTasksLoading, importTasksError,
    selectedImportTaskDetails: current?.details || null,
    selectedImportTaskPreview: current?.preview || null,
  };
}
