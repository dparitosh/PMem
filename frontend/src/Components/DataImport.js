import React, { useState } from 'react';
import axios from 'axios';
import '../CSS/TCSColors.css';

const DataImport = () => {
  const [file, setFile] = useState(null);
  const [nodeDefinitions, setNodeDefinitions] = useState([]);
  const [relationshipDefinitions, setRelationshipDefinitions] = useState([]);
  const [indexes, setIndexes] = useState([]);
  const [constraints, setConstraints] = useState([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [activeSection, setActiveSection] = useState('nodes');

  const handleFileChange = (e) => {
    setFile(e.target.files[0]);
  };

  const addNodeDefinition = () => {
    setNodeDefinitions([...nodeDefinitions, { label: '', properties: [], mergeKeys: [] }]);
  };

  const updateNodeDefinition = (index, field, value) => {
    const updated = [...nodeDefinitions];
    updated[index][field] = value;
    setNodeDefinitions(updated);
  };

  const removeNodeDefinition = (index) => {
    setNodeDefinitions(nodeDefinitions.filter((_, i) => i !== index));
  };

  const addRelationshipDefinition = () => {
    setRelationshipDefinitions([...relationshipDefinitions, { type: '', fromLabel: '', toLabel: '', fromProperty: '', toProperty: '' }]);
  };

  const updateRelationshipDefinition = (index, field, value) => {
    const updated = [...relationshipDefinitions];
    updated[index][field] = value;
    setRelationshipDefinitions(updated);
  };

  const removeRelationshipDefinition = (index) => {
    setRelationshipDefinitions(relationshipDefinitions.filter((_, i) => i !== index));
  };

  const addIndex = () => {
    setIndexes([...indexes, { type: 'range', name: '', label: '', properties: [] }]);
  };

  const updateIndex = (index, field, value) => {
    const updated = [...indexes];
    updated[index][field] = value;
    setIndexes(updated);
  };

  const removeIndex = (index) => {
    setIndexes(indexes.filter((_, i) => i !== index));
  };

  const addConstraint = () => {
    setConstraints([...constraints, { type: 'unique', name: '', label: '', properties: [] }]);
  };

  const updateConstraint = (index, field, value) => {
    const updated = [...constraints];
    updated[index][field] = value;
    setConstraints(updated);
  };

  const removeConstraint = (index) => {
    setConstraints(constraints.filter((_, i) => i !== index));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file) {
      setMessage('Please select a file.');
      return;
    }
    setLoading(true);
    setMessage('');

    const formData = new FormData();
    formData.append('file', file);
    formData.append('nodeDefinitions', JSON.stringify(nodeDefinitions));
    formData.append('relationshipDefinitions', JSON.stringify(relationshipDefinitions));
    formData.append('indexes', JSON.stringify(indexes));
    formData.append('constraints', JSON.stringify(constraints));

    try {
      const response = await axios.post('http://localhost:8000/api/ingest-data', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      setMessage('Data ingestion completed successfully!');
      console.log(response.data);
    } catch (error) {
      setMessage('Error during ingestion: ' + error.response?.data?.detail || error.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container-fluid p-4 data-import-tcs">
      <div className="row">
        <div className="col-12">
          <h2 className="text-dark mb-4">Data Ingestion</h2>
          <p className="text-muted mb-4">Upload CSV or Excel files to import data into Neo4j</p>

          {message && (
            <div className={`alert ${message.includes('Error') ? 'alert-danger' : 'alert-success'} mb-4`}>
              {message}
            </div>
          )}

          <form onSubmit={handleSubmit}>
            {/* File Upload Section */}
            <div className="card mb-4">
              <div className="card-header bg-light">
                <h5 className="mb-0">1. Upload File</h5>
              </div>
              <div className="card-body">
                <div className="mb-3">
                  <label htmlFor="fileUpload" className="form-label">Choose CSV or Excel file</label>
                  <input
                    type="file"
                    className="form-control"
                    id="fileUpload"
                    accept=".csv,.xlsx,.xls"
                    onChange={handleFileChange}
                  />
                  {file && (
                    <div className="mt-2 text-success">
                      <small>Selected: {file.name} ({(file.size / 1024).toFixed(2)} KB)</small>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Configuration Section */}
            <div className="card mb-4">
              <div className="card-header bg-light">
                <h5 className="mb-0">2. Configure Import</h5>
              </div>
              <div className="card-body">
                {/* Section Tabs */}
                <ul className="nav nav-tabs mb-3">
                  <li className="nav-item">
                    <button
                      className={`nav-link ${activeSection === 'nodes' ? 'active' : ''}`}
                      type="button"
                      onClick={() => setActiveSection('nodes')}
                    >
                      Nodes
                    </button>
                  </li>
                  <li className="nav-item">
                    <button
                      className={`nav-link ${activeSection === 'relationships' ? 'active' : ''}`}
                      type="button"
                      onClick={() => setActiveSection('relationships')}
                    >
                      Relationships
                    </button>
                  </li>
                  <li className="nav-item">
                    <button
                      className={`nav-link ${activeSection === 'indexes' ? 'active' : ''}`}
                      type="button"
                      onClick={() => setActiveSection('indexes')}
                    >
                      Indexes
                    </button>
                  </li>
                  <li className="nav-item">
                    <button
                      className={`nav-link ${activeSection === 'constraints' ? 'active' : ''}`}
                      type="button"
                      onClick={() => setActiveSection('constraints')}
                    >
                      Constraints
                    </button>
                  </li>
                </ul>

                {/* Nodes Section */}
                {activeSection === 'nodes' && (
                  <div>
                    <div className="d-flex justify-content-between align-items-center mb-3">
                      <h6 className="mb-0">Node Definitions</h6>
                      <button type="button" className="btn btn-sm" style={{backgroundColor:'#004B87 !important', color:'white !important', border:'1px solid #004B87 !important'}} onClick={addNodeDefinition}>
                        <i className="bi bi-plus-circle"></i> Add Node
                      </button>
                    </div>
                    {nodeDefinitions.map((node, index) => (
                      <div key={index} className="card mb-3">
                        <div className="card-body">
                          <div className="row g-3">
                            <div className="col-md-3">
                              <label className="form-label">Label</label>
                              <input
                                type="text"
                                className="form-control"
                                placeholder="Node Label"
                                value={node.label}
                                onChange={(e) => updateNodeDefinition(index, 'label', e.target.value)}
                              />
                            </div>
                            <div className="col-md-4">
                              <label className="form-label">Properties</label>
                              <input
                                type="text"
                                className="form-control"
                                placeholder="prop1,prop2,prop3"
                                value={node.properties.join(', ')}
                                onChange={(e) => updateNodeDefinition(index, 'properties', e.target.value.split(',').map(s => s.trim()))}
                              />
                            </div>
                            <div className="col-md-4">
                              <label className="form-label">Merge Keys</label>
                              <input
                                type="text"
                                className="form-control"
                                placeholder="key1,key2"
                                value={node.mergeKeys.join(', ')}
                                onChange={(e) => updateNodeDefinition(index, 'mergeKeys', e.target.value.split(',').map(s => s.trim()))}
                              />
                            </div>
                            <div className="col-md-1 d-flex align-items-end">
                              <button type="button" className="btn btn-outline-danger btn-sm" onClick={() => removeNodeDefinition(index)}>
                                <i className="bi bi-trash"></i>
                              </button>
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Relationships Section */}
                {activeSection === 'relationships' && (
                  <div>
                    <div className="d-flex justify-content-between align-items-center mb-3">
                      <h6 className="mb-0">Relationship Definitions</h6>
                      <button type="button" className="btn btn-sm" style={{backgroundColor:'#004B87 !important', color:'white !important', border:'1px solid #004B87 !important'}} onClick={addRelationshipDefinition}>
                        <i className="bi bi-plus-circle"></i> Add Relationship
                      </button>
                    </div>
                    {relationshipDefinitions.map((rel, index) => (
                      <div key={index} className="card mb-3">
                        <div className="card-body">
                          <div className="row g-3">
                            <div className="col-md-2">
                              <label className="form-label">Type</label>
                              <input
                                type="text"
                                className="form-control"
                                placeholder="RELATES_TO"
                                value={rel.type}
                                onChange={(e) => updateRelationshipDefinition(index, 'type', e.target.value)}
                              />
                            </div>
                            <div className="col-md-2">
                              <label className="form-label">From Label</label>
                              <input
                                type="text"
                                className="form-control"
                                placeholder="Source"
                                value={rel.fromLabel}
                                onChange={(e) => updateRelationshipDefinition(index, 'fromLabel', e.target.value)}
                              />
                            </div>
                            <div className="col-md-2">
                              <label className="form-label">To Label</label>
                              <input
                                type="text"
                                className="form-control"
                                placeholder="Target"
                                value={rel.toLabel}
                                onChange={(e) => updateRelationshipDefinition(index, 'toLabel', e.target.value)}
                              />
                            </div>
                            <div className="col-md-2">
                              <label className="form-label">From Property</label>
                              <input
                                type="text"
                                className="form-control"
                                placeholder="id"
                                value={rel.fromProperty}
                                onChange={(e) => updateRelationshipDefinition(index, 'fromProperty', e.target.value)}
                              />
                            </div>
                            <div className="col-md-2">
                              <label className="form-label">To Property</label>
                              <input
                                type="text"
                                className="form-control"
                                placeholder="id"
                                value={rel.toProperty}
                                onChange={(e) => updateRelationshipDefinition(index, 'toProperty', e.target.value)}
                              />
                            </div>
                            <div className="col-md-1 d-flex align-items-end">
                              <button type="button" className="btn btn-outline-danger btn-sm" onClick={() => removeRelationshipDefinition(index)}>
                                <i className="bi bi-trash"></i>
                              </button>
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Indexes Section */}
                {activeSection === 'indexes' && (
                  <div>
                    <div className="d-flex justify-content-between align-items-center mb-3">
                      <h6 className="mb-0">Indexes</h6>
                      <button type="button" className="btn btn-sm" style={{backgroundColor:'#004B87 !important', color:'white !important', border:'1px solid #004B87 !important'}} onClick={addIndex}>
                        <i className="bi bi-plus-circle"></i> Add Index
                      </button>
                    </div>
                    {indexes.map((idx, index) => (
                      <div key={index} className="card mb-3">
                        <div className="card-body">
                          <div className="row g-3">
                            <div className="col-md-2">
                              <label className="form-label">Type</label>
                              <select
                                className="form-select"
                                value={idx.type}
                                onChange={(e) => updateIndex(index, 'type', e.target.value)}
                              >
                                <option value="range">Range</option>
                                <option value="text">Text</option>
                                <option value="fulltext">Fulltext</option>
                                <option value="vector">Vector</option>
                              </select>
                            </div>
                            <div className="col-md-3">
                              <label className="form-label">Name</label>
                              <input
                                type="text"
                                className="form-control"
                                placeholder="index_name"
                                value={idx.name}
                                onChange={(e) => updateIndex(index, 'name', e.target.value)}
                              />
                            </div>
                            <div className="col-md-3">
                              <label className="form-label">Label</label>
                              <input
                                type="text"
                                className="form-control"
                                placeholder="NodeLabel"
                                value={idx.label}
                                onChange={(e) => updateIndex(index, 'label', e.target.value)}
                              />
                            </div>
                            <div className="col-md-3">
                              <label className="form-label">Properties</label>
                              <input
                                type="text"
                                className="form-control"
                                placeholder="prop1,prop2"
                                value={idx.properties.join(', ')}
                                onChange={(e) => updateIndex(index, 'properties', e.target.value.split(',').map(s => s.trim()))}
                              />
                            </div>
                            <div className="col-md-1 d-flex align-items-end">
                              <button type="button" className="btn btn-outline-danger btn-sm" onClick={() => removeIndex(index)}>
                                <i className="bi bi-trash"></i>
                              </button>
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Constraints Section */}
                {activeSection === 'constraints' && (
                  <div>
                    <div className="d-flex justify-content-between align-items-center mb-3">
                      <h6 className="mb-0">Constraints</h6>
                      <button type="button" className="btn btn-sm" style={{backgroundColor:'#004B87 !important', color:'white !important', border:'1px solid #004B87 !important'}} onClick={addConstraint}>
                        <i className="bi bi-plus-circle"></i> Add Constraint
                      </button>
                    </div>
                    {constraints.map((con, index) => (
                      <div key={index} className="card mb-3">
                        <div className="card-body">
                          <div className="row g-3">
                            <div className="col-md-2">
                              <label className="form-label">Type</label>
                              <select
                                className="form-select"
                                value={con.type}
                                onChange={(e) => updateConstraint(index, 'type', e.target.value)}
                              >
                                <option value="unique">Unique</option>
                                <option value="exists">Exists</option>
                                <option value="node_key">Node Key</option>
                              </select>
                            </div>
                            <div className="col-md-3">
                              <label className="form-label">Name</label>
                              <input
                                type="text"
                                className="form-control"
                                placeholder="constraint_name"
                                value={con.name}
                                onChange={(e) => updateConstraint(index, 'name', e.target.value)}
                              />
                            </div>
                            <div className="col-md-3">
                              <label className="form-label">Label</label>
                              <input
                                type="text"
                                className="form-control"
                                placeholder="NodeLabel"
                                value={con.label}
                                onChange={(e) => updateConstraint(index, 'label', e.target.value)}
                              />
                            </div>
                            <div className="col-md-3">
                              <label className="form-label">Properties</label>
                              <input
                                type="text"
                                className="form-control"
                                placeholder="prop1,prop2"
                                value={con.properties.join(', ')}
                                onChange={(e) => updateConstraint(index, 'properties', e.target.value.split(',').map(s => s.trim()))}
                              />
                            </div>
                            <div className="col-md-1 d-flex align-items-end">
                              <button type="button" className="btn btn-outline-danger btn-sm" onClick={() => removeConstraint(index)}>
                                <i className="bi bi-trash"></i>
                              </button>
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Import Button */}
            <div className="d-flex justify-content-end">
              <button
                type="submit"
                className="btn btn-lg"
                style={{backgroundColor:'#004B87 !important', color:'white !important', border:'1px solid #004B87 !important'}}
                disabled={loading || !file}
              >
                {loading ? (
                  <>
                    <span className="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                    Importing...
                  </>
                ) : (
                  <>
                    <i className="bi bi-upload me-2"></i>
                    Import Data
                  </>
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};

export default DataImport;