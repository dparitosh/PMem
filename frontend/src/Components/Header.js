import React from 'react'

const Header = () => {
  return (
    <div style={{ height:'8vh', backgroundColor:'#2c3e50', display:'flex', alignItems:'center', paddingLeft:'20px', boxShadow:'0 2px 4px rgba(0,0,0,0.1)' }}>
      <h1 style={{ color:'white', margin:0, fontSize:'24px', fontWeight:'600' }}>
        DEPO: Digital Engineering Product Ontology Knowledge Graph
      </h1>
    </div>
  );
};

export default Header
