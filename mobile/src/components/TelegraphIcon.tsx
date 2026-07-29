/**
 * Custom telegraph key (Morse code manipulator) vector icon.
 * Replaces a generic phone icon per UX-DR6.
 * Rendered as SVG using react-native-svg.
 */
import React from 'react';
import Svg, { Rect, Circle, Ellipse, Line } from 'react-native-svg';
import { colors } from '../theme/tokens';

interface TelegraphIconProps {
  size?: number;
  color?: string;
  accent?: string;
}

export default function TelegraphIcon({
  size = 160,
  color = colors.gold,
  accent = colors.goldLight,
}: TelegraphIconProps) {
  // ViewBox: 0 0 200 130
  const scale = size / 200;

  return (
    <Svg
      width={size}
      height={size * (130 / 200)}
      viewBox="0 0 200 130"
      accessibilityLabel="Icône manipulateur télégraphique"
      accessibilityRole="image"
    >
      {/* ── Base plate (heavy rectangular block) ── */}
      <Rect x={15} y={100} width={170} height={22} rx={6} fill={color} />
      {/* top-edge highlight on base */}
      <Rect x={15} y={100} width={170} height={4} rx={6} fill={accent} />

      {/* ── Left support column ── */}
      <Rect x={35} y={62} width={14} height={42} rx={4} fill={color} />

      {/* ── Right support column ── */}
      <Rect x={151} y={62} width={14} height={42} rx={4} fill={color} />

      {/* ── Pivot crossbar (horizontal bar connecting the two posts) ── */}
      <Rect x={35} y={76} width={130} height={9} rx={4} fill={colors.burgundy} opacity={0.5} />

      {/* ── Lever arm (the main horizontal bar, slightly raised on right) ── */}
      <Rect x={10} y={52} width={165} height={13} rx={6} fill={color} />

      {/* ── Lever arm top edge highlight ── */}
      <Rect x={10} y={52} width={165} height={3} rx={6} fill={accent} />

      {/* ── Knob stem (vertical connector between lever and knob ball) ── */}
      <Rect x={167} y={36} width={11} height={19} rx={3} fill={color} />

      {/* ── Knob dome (the button you press to generate dots/dashes) ── */}
      <Ellipse cx={172} cy={36} rx={14} ry={8} fill={color} />
      <Ellipse cx={172} cy={33} rx={12} ry={11} fill={color} />
      {/* highlight on dome */}
      <Ellipse cx={167} cy={28} rx={5} ry={4} fill={accent} opacity={0.7} />

      {/* ── Contact screw (gold accent under right end of lever) ── */}
      <Rect x={162} y={65} width={6} height={14} rx={2} fill={accent} />

      {/* ── Spring / coil suggestion at left end ── */}
      <Line x1={20} y1={65} x2={20} y2={52} stroke={color} strokeWidth={3} />
      <Circle cx={20} cy={68} r={5} fill={color} />
      <Circle cx={20} cy={75} r={4} fill={color} opacity={0.7} />
      <Circle cx={20} cy={81} r={3} fill={color} opacity={0.5} />

      {/* ── Contact terminal (small binding post at far left of base) ── */}
      <Circle cx={28} cy={106} r={5} fill={accent} />
      <Circle cx={172} cy={106} r={5} fill={accent} />
    </Svg>
  );
}
