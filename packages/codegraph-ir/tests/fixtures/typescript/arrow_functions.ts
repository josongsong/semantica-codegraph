// Arrow functions
export const add = (a: number, b: number): number => {
  return a + b;
};

// Single expression arrow function
export const multiply = (a: number, b: number): number => a * b;

// Async arrow function
export const fetchData = async (url: string): Promise<Response> => {
  return await fetch(url);
};

// Arrow function with generic
export const map = <T, U>(arr: T[], fn: (item: T) => U): U[] => {
  return arr.map(fn);
};

// Higher-order function
export const createAdder = (x: number) => (y: number) => x + y;

const add5 = createAdder(5);
const result = add5(10); // 15
