export default function AppLoading() {
  return (
    <div className="grid gap-6">
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="skeleton-block h-36" />
        <div className="skeleton-block h-36" />
        <div className="skeleton-block h-36" />
      </div>
      <div className="skeleton-block h-105" />
    </div>
  );
}
