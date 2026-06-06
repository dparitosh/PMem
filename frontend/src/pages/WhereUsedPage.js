import React from 'react';
import WhereUsedView from '../Components/WhereUsedView';
import GraphWidget from '../widgets/GraphWidget';

export default function WhereUsedPage(props) {
  return (
    <div className="depo-page" style={{ height: '100%' }}>
      <GraphWidget title="Where Used Analysis" minHeight={620}>
        <WhereUsedView {...props} />
      </GraphWidget>
    </div>
  );
}
