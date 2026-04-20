import React from 'react';

interface LogoProps {
  className?: string;
  showText?: boolean;
  id?: string;
  textColor?: string;
}

const VisionSafeLogo: React.FC<LogoProps> = ({ className = "w-32 h-32", showText = false, id, textColor = "#FFFFFF" }) => {
  // Adjust viewBox based on content: 
  // Symbol fits in 200x200. With text, we extend height to ~250.
  const viewBox = showText ? "0 0 200 250" : "0 0 200 200";
  const uniqueId = id || 'vs-logo';

  return (
    <div className={`flex flex-col items-center justify-center transition-all duration-500 ease-out hover:scale-110 hover:drop-shadow-[0_0_25px_rgba(255,106,0,0.6)] group ${className}`}>
      <svg
        id={uniqueId}
        viewBox={viewBox}
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="w-full h-full"
        preserveAspectRatio="xMidYMid meet"
      >
        <defs>
          <filter id="vs-glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feColorMatrix in="blur" type="matrix" values="1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 0 0 0 0.8 0" result="glow" />
            <feComposite in="SourceGraphic" in2="glow" operator="over" />
          </filter>
          <linearGradient id="vs-orangeGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#FF6A00" />
            <stop offset="100%" stopColor="#FF8C32" />
          </linearGradient>
          <style>
            {`
              .vs-font { font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; font-weight: 700; }
            `}
          </style>
        </defs>

        {/* --- Symbol Group --- */}
        <g>
            {/* 
               Outer Ring: 4 Equal Segments
               Circumference of r=90 is approx 565. 
               We need 4 equal parts. 565 / 4 = 141.25 per section.
               Dash 100, Gap 41.3
               Slower animation: 12s
            */}
            <path
              id="vs-rotating-ring-outer"
              d="M100 10 A 90 90 0 1 1 100 190 A 90 90 0 1 1 100 10"
              stroke="url(#vs-orangeGradient)"
              strokeWidth="3"
              strokeLinecap="round"
              fill="none"
              strokeDasharray="100 41.3"
              className="origin-center animate-[spin_12s_linear_infinite]"
              style={{ transformOrigin: '100px 100px' }}
              opacity="0.9"
            />
            
            {/* 
               Inner Ring: 8 Equal Segments (Reverse Rotation)
               Circumference of r=78 is approx 490.
               490 / 8 = 61.25 per section.
               Let's do Dash 35 and Gap 26.25
               Slower animation: 8s
            */}
            <path
              id="vs-rotating-ring-inner"
              d="M100 22 A 78 78 0 1 1 100 178 A 78 78 0 1 1 100 22"
              stroke="#FF6A00"
              strokeWidth="1.5"
              strokeLinecap="round"
              fill="none"
              strokeDasharray="35 26.25" 
              className="origin-center animate-[spin_8s_linear_infinite_reverse]"
              style={{ transformOrigin: '100px 100px' }}
              opacity="0.6"
            />

            {/* Shield */}
            <path
              d="M100 35 L145 55 V95 C145 125 125 150 100 165 C75 150 55 125 55 95 V55 L100 35 Z"
              stroke="#FF6A00"
              strokeWidth="3"
              fill="#0A0A0A"
              filter="url(#vs-glow)"
              className="transition-colors duration-300 group-hover:stroke-[#FF8C32]"
            />

            {/* Eye */}
            <path
              d="M70 100 C70 100 85 85 100 85 C115 85 130 100 130 100 C130 100 115 115 100 115 C85 115 70 100 70 100 Z"
              stroke="#FF6A00"
              strokeWidth="2"
              fill="none"
              className="transition-colors duration-300 group-hover:stroke-[#FF8C32]"
            />

            {/* Eye Pupil Pulse Animation */}
            <circle cx="100" cy="100" r="12" fill="#FF6A00" opacity="0.2">
               <animate attributeName="r" values="10;14;10" dur="2s" repeatCount="indefinite" />
               <animate attributeName="opacity" values="0.2;0.5;0.2" dur="2s" repeatCount="indefinite" />
            </circle>
            <circle cx="100" cy="100" r="6" fill="#FF8C32">
               <animate attributeName="r" values="5;7;5" dur="2s" repeatCount="indefinite" />
            </circle>
            
            {/* Tech Details */}
            <path d="M100 35 V45" stroke="#FF6A00" strokeWidth="1" />
            <path d="M100 155 V165" stroke="#FF6A00" strokeWidth="1" />
        </g>

        {/* --- Text Group --- */}
        {showText && (
          <text 
            x="100" 
            y="235" 
            textAnchor="middle" 
            fill={textColor}
            fontSize="24"
            className="vs-font"
            letterSpacing="0.5"
          >
            VISIONSAFE <tspan fill="#FF6A00">360</tspan>
          </text>
        )}
      </svg>
    </div>
  );
};

export default VisionSafeLogo;