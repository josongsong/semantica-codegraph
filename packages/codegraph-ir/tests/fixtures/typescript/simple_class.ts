/**
 * Simple TypeScript class for testing
 */
@Component({
  selector: 'app-user',
  templateUrl: './user.component.html'
})
export class UserComponent {
  private name: string;
  public age: number;

  constructor(name: string, age: number) {
    this.name = name;
    this.age = age;
  }

  public getName(): string {
    return this.name;
  }

  public async fetchData(): Promise<void> {
    // Async method
  }
}
