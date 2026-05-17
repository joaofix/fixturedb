# Test Framework Gaps Analysis

## Java Gaps

### 1. TestNG @DataProvider (Data-driven fixture setup)
```java
@Test
public class DataProviderTests {
    @DataProvider(name = "testData")
    public Object[][] provideTestData() {
        return new Object[][] {
            {"user1", "pass1"},
            {"user2", "pass2"}
        };
    }
    
    @Test(dataProvider = "testData")
    public void testWithData(String user, String pass) { }
}
```
**Status:** ❓ UNTESTED - @DataProvider is not in JUNIT_FIXTURE_ANNOTATIONS

### 2. Spring Test @Before/@After (Spring context aware)
```java
@SpringBootTest
public class SpringIntegrationTest {
    @Before
    public void setUp() {
        // Spring-injected beans
    }
}
```
**Status:** ✅ DETECTED (via @Before) but context not captured

### 3. Arquillian @Deployment
```java
@RunWith(Arquillian.class)
public class DeploymentTest {
    @Deployment
    public static JavaArchive createDeployment() {
        return ShrinkWrap.create(JavaArchive.class);
    }
}
```
**Status:** ❌ NOT DETECTED - @Deployment not covered

### 4. Spock Framework (Groovy) setup/cleanup
```groovy
class SpockTest extends Specification {
    void setupSpec() { }
    void setup() { }
    void cleanup() { }
    void cleanupSpec() { }
}
```
**Status:** ❌ NOT DETECTED - Groovy not supported language

---

## JavaScript/TypeScript Gaps

### 1. Vitest Framework
```typescript
import { describe, beforeEach, afterEach, it, vi } from 'vitest';

describe('Suite', () => {
    beforeEach(async () => {
        // setup
    });
});
```
**Status:** ✅ PARTIALLY - beforeEach/afterEach work (generic), but vitest-specific hooks not mapped

**Missing patterns:**
- `vi.mock()` setup hooks
- `vi.spyOn()` patterns
- Vitest-specific lifecycle

### 2. Jasmine Framework
```typescript
describe('Suite', () => {
    beforeEach(() => { });
    afterEach(() => { });
    beforeAll(() => { });
    afterAll(() => { });
});
```
**Status:** ✅ LIKELY WORKS - Same call patterns as Jest, but not explicitly in tests

### 3. AVA Framework
```typescript
import test from 'ava';

test.before(t => {
    t.context.db = new Database();
});

test.after(t => {
    t.context.db.close();
});

test.serial.before(t => { });
```
**Status:** ❌ NOT DETECTED - Different pattern (test.before instead of beforeEach)

### 4. Cypress Test Fixtures
```typescript
describe('UI Tests', () => {
    before(() => { });
    beforeEach(() => { });
    afterEach(() => { });
});
```
**Status:** ✅ LIKELY WORKS - Standard Mocha hook patterns

---

## Python Gaps

### 1. pytest-asyncio Specific Patterns
```python
@pytest.mark.asyncio
async def test_async():
    fixture = await async_fixture()
```
**Status:** ✅ WORKS - Async fixtures already detected

### 2. pytest Fixture with autouse
```python
@pytest.fixture(autouse=True)
def auto_setup():
    yield
```
**Status:** ✅ DETECTED - scope/autouse distinction not captured

### 3. pytest Fixture with indirect parametrization
```python
@pytest.fixture
def fixture(request):
    return request.param
    
def test_func(fixture):
    pass
```
**Status:** ✅ DETECTED - but indirect param binding not analyzed

---

## Go Gaps

### 1. testify/suite Pattern
```go
type UserSuite struct {
    suite.Suite
    db *sql.DB
}

func (suite *UserSuite) SetupSuite() { }
func (suite *UserSuite) TearDownSuite() { }
func (suite *UserSuite) SetupTest() { }
func (suite *UserSuite) TearDownTest() { }
```
**Status:** ❌ NOT DETECTED - Testify not in heuristics

### 2. Table-driven Tests with shared setup
```go
func TestWithSetup(t *testing.T) {
    tests := []struct {
        name string
        setup func()
    }{
        {"test1", func() { /* setup */ }},
    }
}
```
**Status:** ⚠️ PARTIAL - setup function might be detected as helper

---

## C# Gaps

### 1. xUnit Fixture Class Injection
```csharp
public class DatabaseFixture : IDisposable {
    public DatabaseFixture() { }
    public void Dispose() { }
}

public class Tests : IClassFixture<DatabaseFixture> {
}
```
**Status:** ❓ UNTESTED - IDisposable not in fixture detection

### 2. NUnit SetUpFixture (assembly-level)
```csharp
[SetUpFixture]
public class GlobalSetup {
    [OneTimeSetUp]
    public void GlobalSetup() { }
}
```
**Status:** ⚠️ PARTIAL - @OneTimeSetUp detected but @SetUpFixture class not marked

---

## Summary of Missing Patterns

| Framework | Pattern | Status | Priority |
|-----------|---------|--------|----------|
| Java TestNG | @DataProvider | ❌ | HIGH |
| Java | @Deployment (Arquillian) | ❌ | LOW |
| Java | Static initializers | ❌ | MEDIUM |
| JS/TS | AVA test.before/test.after | ❌ | MEDIUM |
| JS/TS | Vitest explicit typing | ⚠️ | LOW |
| Go | testify/suite.Suite | ❌ | MEDIUM |
| C# | xUnit IDisposable | ❓ | MEDIUM |
| C# | @SetUpFixture class | ⚠️ | LOW |

