import React, { Suspense } from 'react';
import ErrorBoundary from '../Components/ErrorBoundary';
import { resolvePage } from './pageRegistry';

function PageLoadingState() {
  return <div className="depo-page-loading" role="status" aria-live="polite" aria-busy="true"><span className="depo-page-loading__skeleton" aria-hidden="true" />Loading workspace…</div>;
}

export default function AppPageOutlet({ page, pageContext }) {
  const route = resolvePage(page);
  const PageComponent = route.component;
  const props = route.props ? route.props(pageContext) : {};

  return (
    <ErrorBoundary key={page}>
      <Suspense fallback={<PageLoadingState />}>
        <PageComponent {...props} onCompanionRecordChange={pageContext?.onCompanionRecordChange} />
      </Suspense>
    </ErrorBoundary>
  );
}
