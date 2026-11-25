import { ErrorState, LoadingState } from "./AsyncState";

interface Controls {
  offset: number;
  loading: boolean;
  error?: Error;
  hasMore: boolean;
  previous: () => void;
  next: () => void;
  retry: () => void;
}

export function PageControls({ page, label }: { page: Controls; label: string }) {
  return <>
    {page.loading && <LoadingState label={`Loading ${label}`} />}
    {page.error && <ErrorState error={page.error} retry={page.retry} />}
    {(page.offset > 0 || page.hasMore) &&
      <div className="input-row" role="group" aria-label={`${label} pages`}>
        <button disabled={!page.offset || page.loading} onClick={page.previous}>Previous {label}</button>
        <button disabled={!page.hasMore || page.loading} onClick={page.next}>Next {label}</button>
      </div>}
  </>;
}
