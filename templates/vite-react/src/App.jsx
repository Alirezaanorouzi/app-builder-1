import { useState } from 'react';

export default function App() {
  const [count, setCount] = useState(0);

  return (
    <main className="app">
      <h1>به اپ‌ساز خوش آمدید</h1>
      <p>پیش‌نمایش زنده با Vite و React</p>
      <button type="button" onClick={() => setCount((c) => c + 1)}>
        شمارنده: {count}
      </button>
    </main>
  );
}