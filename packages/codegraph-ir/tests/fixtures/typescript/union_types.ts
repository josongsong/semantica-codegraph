// Union and Intersection types
type StringOrNumber = string | number;
type Nullable<T> = T | null | undefined;

interface Person {
  name: string;
  age: number;
}

interface Employee {
  employeeId: string;
  department: string;
}

// Intersection type
type EmployeePerson = Person & Employee;

// Function with union parameter
function process(value: string | number | boolean): void {
  if (typeof value === "string") {
    console.log(value.toUpperCase());
  }
}

// Tuple type
type Coordinate = [number, number];

const point: Coordinate = [10, 20];
