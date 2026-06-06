import React, { useEffect, useMemo, useState } from 'react';

const C = {
  primary: '#004B87',
  primaryDark: '#003366',
  primaryLight: '#E8F1FC',
  green: '#28A745',
  orange: '#FFC107',
  red: '#D32F2F',
  textPrimary: '#1A2B3C',
  textMuted: '#6C757D',
  border: '#E9ECEF',
  borderDark: '#CED4DA',
  bg: '#F8F9FA',
  surface: '#FFFFFF',
};

const getGenerationOptionsForFileType = (fileType) => {
  if (fileType === 'xsd') {
    return [
      { value: 'shacl', label: 'SHACL (RDF Shapes) - Recommended for XSD' },
      { value: 'owl', label: 'OWL (Web Ontology Language)' },
      { value: 'both', label: 'Both SHACL and OWL' }
    ];
  }
  if (fileType === 'xmi' || fileType === 'mdxml') {
    return [
      { value: 'owl', label: 'OWL (Web Ontology Language) - Recommended for XMI/MagicDraw' },
      { value: 'shacl', label: 'SHACL (RDF Shapes)' },
      { value: 'both', label: 'Both OWL and SHACL' }
    ];
  }
  if (['owl', 'rdf', 'ttl'].includes(fileType)) {
    return [
      { value: 'as_is', label: 'As Is (register ontology directly without conversion)' },
    ];
  }

  return [];
};

/**
 * OntologyMetadataForm
 * 
 * Captures ontology metadata before upload:
 * - Ontology Name (customizable label)
 * - Prefix (customizable label)
 * - File Type & Generation Target
 * - Description
 */
export default function OntologyMetadataForm({
  onSubmit,
  onCancel,
  selectedFile,
  isLoading = false,
  initialValues = null,
  formTitle = 'Ontology Metadata',
  ontologyNamePlaceholder = 'e.g., Product Model',
  prefixPlaceholder = 'e.g., myprefix'
}) {
  const [formData, setFormData] = useState({
    ontologyName: initialValues?.ontologyName || '',
    prefix: initialValues?.prefix || '',
    description: initialValues?.description || '',
    generationType: initialValues?.generationType || '',
    schemaType: initialValues?.schemaType || 'schema',
  });

  const [validationErrors, setValidationErrors] = useState({});

  // Determine file type from selected file
  const getFileType = () => {
    if (!selectedFile) return null;
    const ext = selectedFile.name.split('.').pop().toLowerCase();
    return ext;
  };

  // Check if generation options are empty due to unrecognized file type
  const fileType = getFileType();
  const generationOptions = useMemo(() => getGenerationOptionsForFileType(fileType), [fileType]);
  const showFileTypeError = fileType && generationOptions.length === 0;

  useEffect(() => {
    if (!formData.generationType && generationOptions.length > 0) {
      setFormData(prev => ({
        ...prev,
        generationType: generationOptions[0].value,
      }));
    }
  }, [fileType, generationOptions, formData.generationType]);

  const validateForm = () => {
    const errors = {};
    
    if (!formData.ontologyName.trim()) {
      errors.ontologyName = 'Ontology name is required';
    }
    
    if (!formData.prefix.trim()) {
      errors.prefix = 'Prefix is required';
    } else if (!/^[a-z][a-z0-9_]*$/.test(formData.prefix)) {
      errors.prefix = 'Prefix must start with a lowercase letter and contain only lowercase letters, numbers, or underscores';
    }
    
    if (!formData.generationType) {
      errors.generationType = 'Please select generation type';
    }
    
    setValidationErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    
    if (!validateForm()) {
      return;
    }
    
    const fileType = getFileType();
    const normalizedFileType = fileType === 'mdxml' ? 'xmi' : fileType;
    
    onSubmit({
      ...formData,
      fileType: normalizedFileType,
      selectedFile: selectedFile,
      schemaType: formData.schemaType || 'schema'
    });
  };

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      backgroundColor: 'rgba(0,0,0,0.5)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 9999,
      padding: '20px',
      overflow: 'auto'
    }}>
      <div style={{
        backgroundColor: C.surface,
        borderRadius: '8px',
        maxWidth: '600px',
        width: '100%',
        maxHeight: '90vh',
        boxShadow: '0 10px 40px rgba(0,0,0,0.2)',
        overflow: 'auto',
        margin: 'auto'
      }}>
        {/* Header */}
        <div style={{
          background: C.primary,
          color: 'white',
          padding: '20px',
          fontWeight: 700,
          fontSize: '16px'
        }}>
          🧬 {formTitle}
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} style={{ padding: '24px' }}>
          {/* File Info */}
          <div style={{
            padding: '12px',
            backgroundColor: C.primaryLight,
            borderRadius: '4px',
            marginBottom: '24px',
            fontSize: '12px'
          }}>
            <div><strong>File:</strong> {selectedFile?.name}</div>
            <div><strong>Type:</strong> {fileType?.toUpperCase()}</div>
            <div><strong>Size:</strong> {(selectedFile?.size / 1024).toFixed(2)} KB</div>
          </div>

          {/* Ontology Name */}
          <div style={{ marginBottom: '20px' }}>
            <label style={{
              display: 'block',
              marginBottom: '6px',
              fontWeight: 700,
              fontSize: '13px',
              color: C.primary
            }}>
              Ontology Name *
            </label>
            <input
              type="text"
              placeholder={ontologyNamePlaceholder}
              value={formData.ontologyName}
              onChange={(e) => setFormData({ ...formData, ontologyName: e.target.value })}
              style={{
                width: '100%',
                padding: '10px 12px',
                border: `1px solid ${validationErrors.ontologyName ? C.red : C.borderDark}`,
                borderRadius: '4px',
                fontSize: '13px',
                boxSizing: 'border-box'
              }}
            />
            {validationErrors.ontologyName && (
              <div style={{ color: C.red, fontSize: '11px', marginTop: '4px' }}>
                {validationErrors.ontologyName}
              </div>
            )}
            <div style={{
              fontSize: '11px',
              color: C.textMuted,
              marginTop: '4px'
            }}>
              User-friendly name for this ontology
            </div>
          </div>

          {/* Prefix */}
          <div style={{ marginBottom: '20px' }}>
            <label style={{
              display: 'block',
              marginBottom: '6px',
              fontWeight: 700,
              fontSize: '13px',
              color: C.primary
            }}>
              Namespace Prefix *
            </label>
            <input
              type="text"
              placeholder={prefixPlaceholder}
              value={formData.prefix}
              onChange={(e) => setFormData({ ...formData, prefix: e.target.value.toLowerCase() })}
              style={{
                width: '100%',
                padding: '10px 12px',
                border: `1px solid ${validationErrors.prefix ? C.red : C.borderDark}`,
                borderRadius: '4px',
                fontSize: '13px',
                boxSizing: 'border-box',
                fontFamily: 'monospace'
              }}
            />
            {validationErrors.prefix && (
              <div style={{ color: C.red, fontSize: '11px', marginTop: '4px' }}>
                {validationErrors.prefix}
              </div>
            )}
            <div style={{
              fontSize: '11px',
              color: C.textMuted,
              marginTop: '4px'
            }}>
              Used in URIs: {formData.prefix || 'prefix'}:Entity
            </div>
          </div>

          {/* Generation Type */}
          <div style={{ marginBottom: '20px' }}>
            <label style={{
              display: 'block',
              marginBottom: '6px',
              fontWeight: 700,
              fontSize: '13px',
              color: C.primary
            }}>
              Generate As * {fileType === 'xsd' && <span style={{ fontSize: '11px', color: C.green }}>→ SHACL recommended</span>} {fileType === 'xmi' && <span style={{ fontSize: '11px', color: C.green }}>→ OWL recommended</span>}
            </label>
            {showFileTypeError && (
              <div style={{ color: C.red, fontSize: '11px', marginBottom: '8px', padding: '8px', background: '#FFE5E5', border: `1px solid ${C.red}`, borderRadius: '4px' }}>
                ⚠️ File type ".{fileType}" is not recognized. Supported types: .xsd, .xmi, .owl, .rdf, .ttl
              </div>
            )}
            <select
              value={formData.generationType}
              onChange={(e) => setFormData({ ...formData, generationType: e.target.value })}
              disabled={showFileTypeError}
              style={{
                width: '100%',
                padding: '10px 12px',
                border: `1px solid ${validationErrors.generationType || showFileTypeError ? C.red : C.borderDark}`,
                borderRadius: '4px',
                fontSize: '13px',
                boxSizing: 'border-box',
                opacity: showFileTypeError ? 0.6 : 1,
                cursor: showFileTypeError ? 'not-allowed' : 'pointer'
              }}
            >
              <option key="default-format" value="">{showFileTypeError ? '-- File type not supported --' : '-- Select Format --'}</option>
              {generationOptions.map(opt => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            {validationErrors.generationType && (
              <div style={{ color: C.red, fontSize: '11px', marginTop: '4px' }}>
                {validationErrors.generationType}
              </div>
            )}
          </div>

          {/* File Classification */}
          <div style={{ marginBottom: '20px' }}>
            <fieldset style={{
              border: `1px solid ${C.borderDark}`,
              padding: '15px',
              borderRadius: '4px',
              margin: 0
            }}>
              <legend style={{
                fontSize: '13px',
                fontWeight: 700,
                color: C.primary,
                marginLeft: '-6px',
                paddingLeft: '6px'
              }}>
                File Classification *
              </legend>
              <div style={{ marginBottom: '12px' }}>
                <label style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  cursor: 'pointer',
                  marginBottom: '0'
                }}>
                  <input
                    type="radio"
                    name="schemaType"
                    value="schema"
                    checked={formData.schemaType === 'schema'}
                    onChange={(e) => setFormData({ ...formData, schemaType: e.target.value })}
                    style={{ marginRight: '8px', marginTop: '2px', cursor: 'pointer' }}
                  />
                  <div>
                    <strong style={{ color: C.primary }}>Schema/Ontology</strong>
                    <br/>
                    <span style={{ fontSize: '11px', color: C.textMuted }}>
                      For metadata and standards files (e.g., OMG SysML profile, reference ontologies)
                    </span>
                  </div>
                </label>
              </div>
              <div>
                <label style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  cursor: 'pointer'
                }}>
                  <input
                    type="radio"
                    name="schemaType"
                    value="instance"
                    checked={formData.schemaType === 'instance'}
                    onChange={(e) => setFormData({ ...formData, schemaType: e.target.value })}
                    style={{ marginRight: '8px', marginTop: '2px', cursor: 'pointer' }}
                  />
                  <div>
                    <strong style={{ color: C.primary }}>Instance/Model Data</strong>
                    <br/>
                    <span style={{ fontSize: '11px', color: C.textMuted }}>
                      For concrete implementations (e.g., MBSE models, product data)
                    </span>
                  </div>
                </label>
              </div>
            </fieldset>
          </div>

          {/* Description */}
          <div style={{ marginBottom: '20px' }}>
            <label style={{
              display: 'block',
              marginBottom: '6px',
              fontWeight: 700,
              fontSize: '13px',
              color: C.primary
            }}>
              Description
            </label>
            <textarea
              placeholder="Optional description for this ontology..."
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              style={{
                width: '100%',
                padding: '10px 12px',
                border: `1px solid ${C.borderDark}`,
                borderRadius: '4px',
                fontSize: '13px',
                boxSizing: 'border-box',
                minHeight: '80px',
                fontFamily: 'inherit',
                resize: 'vertical'
              }}
            />
          </div>

          {/* Info Box */}
          <div style={{
            padding: '12px',
            backgroundColor: C.bg,
            borderRadius: '4px',
            marginBottom: '20px',
            fontSize: '12px',
            lineHeight: '1.5',
            color: C.textMuted,
            borderLeft: `3px solid ${C.primary}`
          }}>
            <strong>💾 File will be saved to:</strong>
            <div style={{ fontFamily: 'monospace', marginTop: '4px' }}>
              ontology_uploads/{formData.prefix || 'prefix'}_{'{timestamp}'}
            </div>
            <div style={{ marginTop: '8px' }}>
              <strong>🔄 For future reuse:</strong> Files stored with metadata for easy access
            </div>
          </div>

          {/* Buttons */}
          <div style={{
            display: 'flex',
            gap: '12px',
            justifyContent: 'flex-end'
          }}>
            <button
              type="button"
              onClick={onCancel}
              disabled={isLoading}
              style={{
                padding: '10px 24px',
                border: `1px solid ${C.border}`,
                borderRadius: '4px',
                background: C.surface,
                color: C.textPrimary,
                fontSize: '13px',
                fontWeight: 700,
                cursor: isLoading ? 'not-allowed' : 'pointer',
                opacity: isLoading ? 0.5 : 1
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading}
              style={{
                padding: '10px 24px',
                border: 'none',
                borderRadius: '4px',
                background: C.primary,
                color: 'white',
                fontSize: '13px',
                fontWeight: 700,
                cursor: isLoading ? 'not-allowed' : 'pointer',
                opacity: isLoading ? 0.7 : 1
              }}
            >
              {isLoading ? '[WAIT] Processing...' : '[OK] Upload & Parse'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
