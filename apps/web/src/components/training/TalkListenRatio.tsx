"use client";

interface TalkListenRatioProps {
  /** User talk percentage 0-100 */
  talkPercent: number;
}

export default function TalkListenRatio({ talkPercent }: TalkListenRatioProps) {
  const listenPercent = 100 - talkPercent;

  return (
    <div className="rounded-lg border border-white/10 bg-white/5 p-3">
      <div className="mb-2 font-mono text-[10px] font-medium uppercase tracking-widest text-white/30">
        Talk / Listen
      </div>
      <div className="flex h-2 w-full overflow-hidden rounded-full">
        <div
          className="bg-vh-purple transition-all duration-500"
          style={{ width: `${talkPercent}%` }}
        />
        <div
          className="bg-white/20 transition-all duration-500"
          style={{ width: `${listenPercent}%` }}
        />
      </div>
      <div className="mt-1 flex justify-between font-mono text-[10px] text-white/30">
        <span>{Math.round(talkPercent)}% вы</span>
        <span>{Math.round(listenPercent)}% клиент</span>
      </div>
    </div>
  );
}
