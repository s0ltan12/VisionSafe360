/**
 * Accessibility utilities for WCAG 2.1 AA compliance
 * Includes focus management, ARIA helpers, and keyboard handlers
 */
import type React from 'react';

/**
 * Focus management utilities
 */
export const focusUtils = {
  // Set focus with optional delay for animations
  setFocus: (element: HTMLElement | null, delay = 0) => {
    if (!element) return;
    if (delay > 0) {
      setTimeout(() => element.focus(), delay);
    } else {
      element.focus();
    }
  },

  // Trap focus within a container (useful for modals)
  trapFocus: (container: HTMLElement | null, event: KeyboardEvent) => {
    if (!container || event.key !== 'Tab') return;

    const focusableElements = container.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    const firstElement = focusableElements[0] as HTMLElement;
    const lastElement = focusableElements[focusableElements.length - 1] as HTMLElement;

    if (event.shiftKey) {
      // Shift + Tab
      if (document.activeElement === firstElement) {
        event.preventDefault();
        lastElement.focus();
      }
    } else {
      // Tab
      if (document.activeElement === lastElement) {
        event.preventDefault();
        firstElement.focus();
      }
    }
  },

  // Restore focus after a dialog closes
  restoreFocus: (previousActive: Element | null) => {
    if (previousActive instanceof HTMLElement) {
      previousActive.focus();
    }
  },
};

/**
 * Keyboard event handlers
 */
export const keyboardUtils = {
  isEnterOrSpace: (event: React.KeyboardEvent) => {
    return event.key === 'Enter' || event.key === ' ';
  },

  isEscape: (event: KeyboardEvent | React.KeyboardEvent) => {
    return event.key === 'Escape';
  },

  isArrowKey: (event: KeyboardEvent | React.KeyboardEvent) => {
    return ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(event.key);
  },
};

/**
 * ARIA attribute generators
 */
export const ariaUtils = {
  // Generate describedBy ID
  getDescribedById: (fieldId: string) => `${fieldId}-description`,

  // Generate error ID
  getErrorId: (fieldId: string) => `${fieldId}-error`,

  // Generate help text ID
  getHelpTextId: (fieldId: string) => `${fieldId}-help`,
};

/**
 * CSS class utilities for focus and accessibility states
 */
export const a11yClasses = {
  // Focus ring for keyboard navigation
  focusRing: 'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-vs-orange',

  // Focus ring for dark backgrounds
  focusRingDark: 'focus-visible:ring-2 focus-visible:ring-vs-orange focus-visible:ring-offset-2 focus-visible:ring-offset-[#050505]',

  // High contrast mode support
  highContrast: 'forced-colors:outline forced-colors:outline-current',

  // Reduced motion support
  reducedMotionClass: (animatedClass: string, staticClass: string) => {
    return `${staticClass} ${animatedClass}`;
  },
};

/**
 * Screen reader only content
 */
export const ScreenReaderOnly = ({ children }: { children: React.ReactNode }) => (
  <span
    className="sr-only"
    style={{
      position: 'absolute',
      width: '1px',
      height: '1px',
      padding: 0,
      margin: '-1px',
      overflow: 'hidden',
      clip: 'rect(0, 0, 0, 0)',
      whiteSpace: 'nowrap',
      border: 0,
    }}
  >
    {children}
  </span>
);

/**
 * Loading indicator with accessible announcement
 */
export const AccessibleSpinner = ({ label = 'Loading' }: { label?: string }) => (
  <>
    <div className="w-5 h-5 border-2 border-current border-t-transparent rounded-full animate-spin" />
    <ScreenReaderOnly>{label}...</ScreenReaderOnly>
  </>
);

/**
 * Error message with ARIA live region
 */
export const AccessibleErrorMessage = ({
  id,
  message,
  role = 'alert',
}: {
  id: string;
  message: string;
  role?: 'alert' | 'status';
}) => (
  <div
    id={id}
    role={role}
    aria-live="polite"
    aria-atomic="true"
    className="bg-red-500/10 border border-red-500/50 p-3 rounded-lg flex items-center space-x-3 rtl:space-x-reverse text-red-500 text-sm"
  >
    {message}
  </div>
);

/**
 * Check if element is visible in viewport
 */
export const isElementInViewport = (el: HTMLElement | null): boolean => {
  if (!el) return false;
  const rect = el.getBoundingClientRect();
  return (
    rect.top >= 0 &&
    rect.left >= 0 &&
    rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
    rect.right <= (window.innerWidth || document.documentElement.clientWidth)
  );
};

/**
 * Announce to screen readers (live region)
 */
export const announceToScreenReader = (message: string, type: 'polite' | 'assertive' = 'polite') => {
  const announcement = document.createElement('div');
  announcement.setAttribute('role', 'status');
  announcement.setAttribute('aria-live', type);
  announcement.setAttribute('aria-atomic', 'true');
  announcement.style.position = 'absolute';
  announcement.style.left = '-10000px';
  announcement.textContent = message;
  document.body.appendChild(announcement);

  // Remove after announcement is made
  setTimeout(() => announcement.remove(), 1000);
};
