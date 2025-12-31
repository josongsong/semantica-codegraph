// Generic class with constraints
export class Container<T extends Serializable> {
  private items: Array<T>;

  constructor() {
    this.items = [];
  }

  public add(item: T): void {
    this.items.push(item);
  }

  public get(index: number): T | undefined {
    return this.items[index];
  }
}

// Generic function
function identity<T>(value: T): T {
  return value;
}

// Multiple type parameters
function merge<T, U>(obj1: T, obj2: U): T & U {
  return { ...obj1, ...obj2 };
}
