export function Scanline() {
  return (
    <div className="pointer-events-none fixed inset-0 z-50 overflow-hidden opacity-[0.03]">
      <div className="absolute inset-x-0 h-[2px] animate-scanline bg-vh-purple" />
    </div>
  );
}
