import React from 'react';
import { CameraSafetyZone } from '../types';

const isVisibleZone = (zone: CameraSafetyZone) =>
  zone.enabled && Array.isArray(zone.polygon) && zone.polygon.length >= 3;

const labelWidth = (name: string) => Math.max(82, (name.length + 2) * 11);

const SafetyZonesOverlay: React.FC<{ zones: CameraSafetyZone[] }> = ({ zones }) => {
  const visibleZones = zones.filter(isVisibleZone);
  if (!visibleZones.length) return null;

  const ref = visibleZones[0];
  const sw = ref.sourceWidth || 1280;
  const sh = ref.sourceHeight || 720;

  return (
    <svg
      viewBox={`0 0 ${sw} ${sh}`}
      preserveAspectRatio="xMidYMid meet"
      className="pointer-events-none absolute inset-0 z-10 h-full w-full"
      aria-hidden="true"
    >
      {visibleZones.map((zone) => {
        const points = zone.polygon.map(point => `${point.x},${point.y}`).join(' ');
        const labelPoint = zone.polygon[0];
        const x = Math.min(Math.max(6, labelPoint.x + 6), Math.max(6, sw - labelWidth(zone.name) - 6));
        const y = Math.max(6, labelPoint.y - 30);

        return (
          <g key={zone.id}>
            <polygon
              points={points}
              fill={`${zone.color}26`}
              stroke={zone.color}
              strokeWidth={4}
              strokeDasharray={String(zone.zoneType) === 'allowed' ? '0' : '14 8'}
              vectorEffect="non-scaling-stroke"
            />
            <rect
              x={x}
              y={y}
              width={labelWidth(zone.name)}
              height={26}
              rx={6}
              fill="rgba(0,0,0,0.78)"
              stroke={zone.color}
              strokeWidth={1.5}
              vectorEffect="non-scaling-stroke"
            />
            <text
              x={x + 10}
              y={y + 18}
              fill={zone.color}
              fontSize={16}
              fontWeight={700}
              fontFamily="ui-monospace, SFMono-Regular, monospace"
            >
              {zone.name}
            </text>
          </g>
        );
      })}
    </svg>
  );
};

export default SafetyZonesOverlay;
