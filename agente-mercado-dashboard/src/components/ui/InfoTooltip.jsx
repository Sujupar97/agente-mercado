import { useState, useRef, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { InformationCircleIcon, XMarkIcon } from '@heroicons/react/24/outline';

export function InfoTooltip({ text }) {
  const [show, setShow] = useState(false);
  const [pos, setPos] = useState({ top: 0, left: 0 });
  const btnRef = useRef(null);
  const panelRef = useRef(null);

  const updatePosition = useCallback(() => {
    if (!btnRef.current) return;
    const rect = btnRef.current.getBoundingClientRect();
    const panelWidth = 320;
    let left = rect.left + rect.width / 2 - panelWidth / 2;

    // Mantener dentro de la pantalla
    if (left < 8) left = 8;
    if (left + panelWidth > window.innerWidth - 8) {
      left = window.innerWidth - panelWidth - 8;
    }

    // Mostrar arriba del boton; si no cabe, mostrar abajo
    let top = rect.top - 12;
    const showBelow = top < 120;

    setPos({
      top: showBelow ? rect.bottom + 8 : top,
      left,
      showBelow,
    });
  }, []);

  useEffect(() => {
    if (!show) return;
    updatePosition();

    function handleClickOutside(e) {
      if (
        panelRef.current && !panelRef.current.contains(e.target) &&
        btnRef.current && !btnRef.current.contains(e.target)
      ) {
        setShow(false);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    window.addEventListener('scroll', updatePosition, true);
    window.addEventListener('resize', updatePosition);

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      window.removeEventListener('scroll', updatePosition, true);
      window.removeEventListener('resize', updatePosition);
    };
  }, [show, updatePosition]);

  return (
    <>
      <button
        ref={btnRef}
        onClick={() => setShow(!show)}
        className="inline-flex ml-1.5 focus:outline-none"
        aria-label="Ver explicacion"
      >
        <InformationCircleIcon
          className={`w-4 h-4 cursor-pointer transition-colors ${
            show ? 'text-blue-400' : 'text-gray-500 hover:text-gray-300'
          }`}
        />
      </button>

      {show && createPortal(
        <div
          ref={panelRef}
          style={{
            position: 'fixed',
            top: pos.showBelow ? pos.top : undefined,
            bottom: pos.showBelow ? undefined : `${window.innerHeight - pos.top}px`,
            left: pos.left,
            zIndex: 9999,
            width: 320,
          }}
        >
          <div className="bg-gray-800 border border-gray-600/50 rounded-xl shadow-2xl p-4 relative">
            <button
              onClick={() => setShow(false)}
              className="absolute top-2 right-2 text-gray-500 hover:text-gray-300"
            >
              <XMarkIcon className="w-4 h-4" />
            </button>
            <p className="text-sm text-gray-200 leading-relaxed pr-5">
              {text}
            </p>
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}
