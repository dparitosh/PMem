import React, { Suspense } from 'react';
import ErrorBoundary from '../Components/ErrorBoundary';
import { resolvePage } from './pageRegistry';

function PageLoadingState() {
  return <div className="depo-page-loading" role="status" aria-live="polite">Loading workspace…</div>;
}

export default function AppPageOutlet({ page, pageContext }) {
  const route = resolvePage(page);
  const PageComponent = route.component;
  const props = route.props ? route.props(pageContext) : {};

  return (
    <ErrorBoundary>
      <Suspense fallback={<PageLoadingState />}>
        <PageComponent {...props} />
      </Suspense>
    </ErrorBoundary>
  );
}
