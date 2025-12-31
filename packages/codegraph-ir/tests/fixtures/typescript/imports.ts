// Various import styles
import React from 'react';
import { useState, useEffect } from 'react';
import * as ReactDOM from 'react-dom';
import { Component as Comp } from '@angular/core';
import type { User, Post } from './types';

// Re-export
export { useState, useEffect } from 'react';
export * from './utils';

// Default export
export default class MyClass {
  name: string;

  constructor(name: string) {
    this.name = name;
  }
}

// Named exports
export const PI = 3.14159;
export function calculate(x: number): number {
  return x * PI;
}
