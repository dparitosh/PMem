import React, { useState, useEffect } from 'react';
import axios from 'axios';

// Simplified clean ReportsTab component with Search + backend report types.
// Generic version - works with any node types
const ReportsTab = ({ searchResults }) => {
    const [activeReport, setActiveReport] = useState('search'); // 'search' or dynamically discovered types
    const [loading, setLoading] = useState(false);
    const [reportData, setReportData] = useState([]); // raw data (search raw or backend fetched)
    const [filteredData, setFilteredData] = useState([]); // filtered & sorted
    const [filters, setFilters] = useState({});
    const [sortColumn, setSortColumn] = useState('');
    const [sortDirection, setSortDirection] = useState('asc');
    const [currentPage, setCurrentPage] = useState(1);
    const [itemsPerPage, setItemsPerPage] = useState(10);
    const [totalItems, setTotalItems] = useState(0);
    const [visibleColumns, setVisibleColumns] = useState({});
    const [showColumnSelector, setShowColumnSelector] = useState(false);
    const [availableTypes, setAvailableTypes] = useState([]); // Dynamically discovered node types

    // ---------- Helpers ----------
    const unwanted = ['x','y','vx','vy','elementId','index','X','Y','VX','VY','elementID'];
    const stripUnwanted = (data) => data.map(r => { const c={...r}; unwanted.forEach(k=>delete c[k]); return c; });

    const processSearchResults = (results) => {
        if (!Array.isArray(results)) return [];
        return stripUnwanted(results.map(item => {
            if (item.n) {
                const node = item.n; const labels=node.labels||[]; const props=node.properties||{};
                return { elementId: node.elementId, type: labels.join(', '), ...props };
            }
            if (item.node) {
                const node=item.node; const labels=item.node_labels||[]; const props=node.properties||node;
                return { elementId: node.elementId, type: labels.join(', '), ...props };
            }
            return item;
        }));
    };

    const formatCellValue = (val) => {
        if (val === null || val === undefined) return '';
        if (typeof val === 'object') return JSON.stringify(val);
        return String(val);
    };

    const getCellTitle = (val) => {
        const text = formatCellValue(val);
        return text ? text : undefined;
    };

    const getDistinctValues = (data,key) => {
        const s=new Set(); data.forEach(r=>{ if(r[key]!==undefined) s.add(String(r[key])); });
        return Array.from(s).sort();
    };

    const getHeaders = (data) => {
        if (!data.length) return [];
        const set=new Set(); data.forEach(r=>Object.keys(r).forEach(k=>set.add(k)));
        return Array.from(set).filter(h=>h!=='elementId');
    };

    const initColumns = (headers) => {
        const init={}; headers.forEach(h=>init[h]=true); setVisibleColumns(init);
    };
    const visibleHeaders = (headers) => headers.filter(h => visibleColumns[h] !== false);
    const toggleColumn = (h) => setVisibleColumns(p => ({ ...p, [h]: p[h] === false ? true : false }));
    const showAllColumns = (headers) => { const o={}; headers.forEach(h=>o[h]=true); setVisibleColumns(o); };
    const hideAllColumns = (headers) => { const o={}; headers.forEach(h=>o[h]=false); setVisibleColumns(o); };

    const applyFilters = (data) => {
        if (activeReport !== 'search' || !Object.keys(filters).length) return data;
        return data.filter(row => Object.entries(filters).every(([k,v]) => !v || String(row[k]) === v));
    };
    const handleFilterChange = (h,val) => { setFilters(p => { const n={...p}; if(!val) delete n[h]; else n[h]=val; return n; }); setCurrentPage(1); };
    const clearFilters = () => setFilters({});

    const handleSort = (h) => {
        setSortDirection(prev => (sortColumn === h && prev === 'asc') ? 'desc' : 'asc');
        setSortColumn(h);
    };
    const sortData = (data) => {
        if (activeReport !== 'search' || !sortColumn) return data;
        const dir = sortDirection === 'asc' ? 1 : -1;
        return [...data].sort((a,b)=>{
            const av=a[sortColumn]; const bv=b[sortColumn];
            if(av===bv) return 0; return av>bv?dir:-dir;
        });
    };

    const pageSlice = (data) => {
        const start=(currentPage-1)*itemsPerPage;
        return data.slice(start,start+itemsPerPage);
    };
    const totalPagesCalc = (len) => Math.ceil((len||0)/itemsPerPage);

    const handlePageChange = (p) => setCurrentPage(p);
    const handleItemsPerPageChange = (n) => { setItemsPerPage(n); setCurrentPage(1); };

    // Backend report fetch
    // Legacy backend report fetch retained for potential future use (currently unused for classification subtabs)
    // eslint-disable-next-line no-unused-vars
    const fetchReport = async (type,page=1) => {
        setLoading(true);
        try {
            const res = await axios.post('http://localhost:8000/reports', { type, page, page_size: itemsPerPage });
            const rows = res.data?.data || [];
            setReportData(stripUnwanted(rows));
            setTotalItems(res.data?.total_items || rows.length);
        } catch(e){ console.error('Report fetch error', e); setReportData([]); setTotalItems(0);} finally { setLoading(false); }
    };

    // Classification helper - Generic version
    const classifyData = (processed, typeFilter) => {
        if (!Array.isArray(processed)) return [];
        if (typeFilter === 'search') return processed; // Show all
        
        const firstLabel = (row) => {
            if (row.type) return row.type.split(',')[0].trim();
            if (row.labels && row.labels.length) return row.labels[0];
            return row.label || '';
        };
        
        // Filter by the selected type
        return processed.filter(r => firstLabel(r) === typeFilter);
    };
    
    // Discover unique node types from search results
    const discoverTypes = (processed) => {
        const types = new Set();
        processed.forEach(row => {
            let type = '';
            if (row.type) type = row.type.split(',')[0].trim();
            else if (row.labels && row.labels.length) type = row.labels[0];
            else if (row.label) type = row.label;
            if (type) types.add(type);
        });
        return Array.from(types).sort();
    };

    // Effect: data pipeline
    useEffect(()=>{
        const processed = processSearchResults(searchResults);
        
        // Discover available types for tabs
        const types = discoverTypes(processed);
        setAvailableTypes(types);
        
        // Apply classification filter
        let base = classifyData(processed, activeReport);
        
        // Apply additional filters and sorting only for search tab
        if (activeReport === 'search') {
            base = applyFilters(base);
            base = sortData(base);
        }
        
        setReportData(processed); // keep full processed for column value sets
        setFilteredData(base);
        setTotalItems(base.length);
        
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [searchResults, activeReport, filters, sortColumn, sortDirection, currentPage, itemsPerPage]);

    // Effect: initialize columns when data shape available
    useEffect(()=>{
        const headers = getHeaders(activeReport==='search' ? filteredData : reportData);
        if (headers.length && Object.keys(visibleColumns).length === 0){ initColumns(headers); }
    }, [reportData, filteredData, activeReport, visibleColumns]);

    // Derived values
    const displayData = pageSlice(filteredData);
    const headersAll = getHeaders(filteredData);
    const headersVis = visibleHeaders(headersAll);
    const totalPages = totalPagesCalc(filteredData.length);
    const startIndex = (currentPage-1)*itemsPerPage;
    const endIndex = Math.min(startIndex+displayData.length, filteredData.length);
    const isSearchDerived = activeReport !== 'search'; // true when viewing a specific type tab

    return (
        <div style={{ minHeight:'100%', padding:'20px' }}>
            {/* Report Selector - Dynamic tabs based on discovered node types */}
            <div className="mb-3">
                <div className="btn-group" role="group" style={{ flexWrap: 'wrap' }}>
                    {/* Always show "All Results" first */}
                    <button
                        key="search"
                        className="btn btn-sm"
                        onClick={()=>{ setActiveReport('search'); setCurrentPage(1); }}
                        style={{ color: activeReport==='search' ? '#fff' : '#004B87', backgroundColor: activeReport==='search'? '#004B87':'#f0f4f8', borderColor:'#004B87', fontWeight:600, fontSize:13 }}
                    >All Results</button>
                    
                    {/* Dynamic type filters */}
                    {availableTypes.map(type => (
                        <button
                            key={type}
                            className="btn btn-sm"
                            onClick={()=>{ setActiveReport(type); setCurrentPage(1); }}
                            style={{ color: activeReport===type ? '#fff' : '#004B87', backgroundColor: activeReport===type? '#004B87':'#f0f4f8', borderColor:'#004B87', fontWeight:600, fontSize:13 }}
                        >{type}</button>
                    ))}
                </div>
            </div>

            {loading && (
                <div className="text-center mb-3"><div className="spinner-border" role="status"><span className="sr-only">Loading...</span></div></div>
            )}

            {/* Column Selector */}
            {headersAll.length>0 && (
                <div className="mb-3">
                    <div className="dropdown" style={{ position:'relative' }}>
                        <button
                            className="btn btn-sm dropdown-toggle"
                            type="button"
                            onClick={()=>setShowColumnSelector(s=>!s)}
                            style={{
                                backgroundColor:'#0a8276',
                                color:'#fff',
                                fontWeight:600,
                                border:'1px solid #0a8276',
                                padding:'6px 12px',
                                boxShadow:'0 2px 4px rgba(0,0,0,0.15)'
                            }}
                        >
                            <i className="fas fa-cog me-1"></i> Columns ({headersVis.length}/{headersAll.length})
                        </button>
                        {showColumnSelector && (
                            <div className="dropdown-menu show p-3" style={{ minWidth:300, maxHeight:400, overflowY:'auto', background:'#0a8276', color:'#fff', border:'1px solid #0a8276', position:'absolute', top:'100%', left:0, zIndex:2000, boxShadow:'0 4px 12px rgba(0,0,0,0.25)' }}>
                                <div className="d-flex justify-content-between mb-2">
                                    <button 
                                      className="btn btn-sm"
                                      onClick={()=>showAllColumns(headersAll)}
                                      style={{
                                        background:'#0a8276',
                                        color:'#fff',
                                        fontSize:12,
                                        padding:'4px 10px',
                                        border:'1px solid #fff',
                                        fontWeight:600
                                      }}
                                    >Show All</button>
                                    <button 
                                      className="btn btn-sm"
                                      onClick={()=>hideAllColumns(headersAll)}
                                      style={{
                                        background:'#0a8276',
                                        color:'#fff',
                                        fontSize:12,
                                        padding:'4px 10px',
                                        border:'1px solid #fff',
                                        fontWeight:600
                                      }}
                                    >Hide All</button>
                                </div>
                                <hr className="my-2" />
                                {headersAll.map(h => (
                                    <div key={h} className="form-check" style={{marginBottom:4}}>
                                        <input 
                                          className="form-check-input" 
                                          type="checkbox" 
                                          id={`col-${h}`} 
                                          checked={visibleColumns[h] !== false} 
                                          onChange={()=>toggleColumn(h)} 
                                          style={{cursor:'pointer'}}
                                        />
                                        <label 
                                          className="form-check-label" 
                                          htmlFor={`col-${h}`}
                                          style={{color:'#fff', fontSize:12}}
                                        >{h.replace(/_/g,' ').toUpperCase()}</label>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Filters (search only) */}
            {activeReport==='search' && headersVis.length>0 && (
                <div className="mb-3 p-3" style={{ background:'#F5F5F5', borderRadius:6 }}>
                    <div className="row g-2 align-items-center">
                        <div className="col-auto"><strong>Filters:</strong></div>
                        {headersVis.slice(0,4).map(h => (
                            <div key={h} className="col-auto">
                                <select
                                    className="form-select form-select-sm"
                                    value={filters[h]||''}
                                    onChange={e=>handleFilterChange(h,e.target.value)}
                                    style={{ minWidth:150 }}
                                >
                                    <option value="">Filter {h.replace(/_/g,' ')}</option>
                                    {getDistinctValues(reportData,h).map(v => <option key={v} value={v}>{v.length>30? v.slice(0,30)+'…': v}</option>)}
                                </select>
                            </div>
                        ))}
                        <div className="col-auto">
                            <button
                                className="btn btn-outline-secondary btn-sm"
                                onClick={clearFilters}
                                disabled={!Object.keys(filters).length}
                                style={{ color:'#333', background:'#f0f4f8', borderColor:'#6C757D', fontWeight:600, opacity:!Object.keys(filters).length?0.6:1 }}
                            >Clear Filters</button>
                        </div>
                    </div>
                </div>
            )}

            {/* Data Table */}
            <div style={{ border:'1px solid #ddd', borderRadius:6, overflow:'auto', height:'calc(100% - 140px)', minHeight:400, background:'#fff' }}>
                {displayData.length===0 ? (
                    <div className="text-center p-4">
                        <p className="text-muted">
                            {activeReport==='search' 
                                ? (Object.keys(filters).length? 'No data matches current filters.' : 'No search results to display.')
                                : `No ${activeReport} found.`
                            }
                        </p>
                    </div>
                ) : (
                    <table className="table table-striped table-hover mb-0">
                        <thead className="sticky-top bg-light">
                            <tr>
                                {headersVis.map(h => (
                                    <th
                                        key={h}
                                        style={{ minWidth:120, fontWeight:'bold', borderBottom:'2px solid #0066B3', cursor: activeReport==='search' ? 'pointer':'default', userSelect:'none' }}
                                        onClick={() => { if(activeReport==='search') handleSort(h); }}
                                    >
                                        <div className="d-flex align-items-center justify-content-between">
                                            <span>{h.replace(/_/g,' ').toUpperCase()}</span>
                                            {activeReport==='search' && (
                                                <span style={{ marginLeft:5, fontSize:12 }}>{sortColumn===h ? (sortDirection==='asc' ? '↑':'↓') : '↕'}</span>
                                            )}
                                        </div>
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {displayData.map((row,i) => (
                                <tr key={i}>
                                    {headersVis.map(h => {
                                        const cellValue = formatCellValue(row[h]);
                                        return (
                                            <td key={h} style={{ maxWidth:200 }}>
                                                <div title={getCellTitle(row[h])} style={{ overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{cellValue}</div>
                                            </td>
                                        );
                                    })}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>

            {/* Pagination & Export */}
            <div className="mt-3 d-flex flex-wrap justify-content-between align-items-center gap-2">
                <div className="d-flex align-items-center">
                    {activeReport==='search' && filteredData.length>0 && (
                        <span className="me-3">Showing {Math.min(startIndex+1, filteredData.length)} to {endIndex} of {filteredData.length} entries</span>
                    )}
                    {activeReport!=='search' && isSearchDerived && totalItems>0 && (
                        <span className="me-3">Showing {Math.min(startIndex+1,totalItems)} to {endIndex} of {totalItems} entries</span>
                    )}
                    {activeReport==='search' && (
                        <div className="d-flex align-items-center">
                            <label className="me-2">Items per page:</label>
                            <select className="form-select form-select-sm" style={{ width:'auto' }} value={itemsPerPage} onChange={e=>handleItemsPerPageChange(parseInt(e.target.value))}>
                                {[10,25,50,100].map(n => <option key={n} value={n}>{n}</option>)}
                            </select>
                        </div>
                    )}
                </div>
                {activeReport==='search' && totalPages>1 && (
                    <nav>
                        <ul className="pagination pagination-sm mb-0">
                            <li className={`page-item ${currentPage===1?'disabled':''}`}><button className="page-link" onClick={()=>handlePageChange(1)} disabled={currentPage===1}>First</button></li>
                            <li className={`page-item ${currentPage===1?'disabled':''}`}><button className="page-link" onClick={()=>handlePageChange(currentPage-1)} disabled={currentPage===1}>Prev</button></li>
                            {(() => { const pages=[]; const start=Math.max(1,currentPage-2); const end=Math.min(totalPages,currentPage+2); for(let p=start;p<=end;p++){ pages.push(<li key={p} className={`page-item ${currentPage===p?'active':''}`}><button className="page-link" onClick={()=>handlePageChange(p)}>{p}</button></li>);} return pages; })()}
                            <li className={`page-item ${currentPage===totalPages?'disabled':''}`}><button className="page-link" onClick={()=>handlePageChange(currentPage+1)} disabled={currentPage===totalPages}>Next</button></li>
                            <li className={`page-item ${currentPage===totalPages?'disabled':''}`}><button className="page-link" onClick={()=>handlePageChange(totalPages)} disabled={currentPage===totalPages}>Last</button></li>
                        </ul>
                    </nav>
                )}
                {displayData.length>0 && (
                    <div className="d-flex gap-2">
                        <button
                            className="btn btn-sm"
                            style={{color:'#333', background:'#f0f4f8', border:'1px solid #6C757D', fontWeight:600}}
                            onClick={()=>{
                                const exportData = isSearchDerived ? filteredData : reportData;
                                const csv = [visibleHeaders(getHeaders(isSearchDerived?filteredData:reportData)).join(','), ...exportData.map(r => visibleHeaders(getHeaders(isSearchDerived?filteredData:reportData)).map(h=>JSON.stringify(r[h]||'')).join(','))].join('\n');
                                const blob=new Blob([csv],{type:'text/csv'}); const url=URL.createObjectURL(blob); const a=document.createElement('a'); a.href=url; a.download=`${activeReport}_all_${new Date().toISOString().split('T')[0]}.csv`; a.click();
                            }}
                        >Export CSV (All)</button>
                        {activeReport==='search' && (
                            <button
                                className="btn btn-sm"
                                style={{color:'#004B87', background:'#e8f4fd', border:'1px solid #004B87', fontWeight:600}}
                                onClick={()=>{
                                    const csv=[headersVis.join(','), ...displayData.map(r => headersVis.map(h=>JSON.stringify(r[h]||'')).join(','))].join('\n');
                                    const blob=new Blob([csv],{type:'text/csv'}); const url=URL.createObjectURL(blob); const a=document.createElement('a'); a.href=url; a.download=`${activeReport}_page_${currentPage}_${new Date().toISOString().split('T')[0]}.csv`; a.click();
                                }}
                            >Export Current Page</button>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
};

export default ReportsTab;

