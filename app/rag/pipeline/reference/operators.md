## Basic operators

Milvus supports several basic operators for filtering data:

- **Comparison Operators** : `==` , `!=` , `>` , `<` , `>=` , and `<=` allow filtering based on numeric or text fields.
- **Range Filters** : `LIKE` help match specific value ranges or sets.
- **Arithmetic Operators** : `+` , `-` , `*` , `/` , `%` , and `**` are used for calculations involving numeric fields.
- **Logical Operators** : `AND` , `OR` , and `NOT` combine multiple conditions into complex expressions.

### Example

To find individuals over the age of 25 living in either "北京" (Beijing) or "上海" (Shanghai), use the following template expression:

```
filter = "age > 25 AND city IN ['北京', '上海']"
```

## Comparison operators

Comparison operators are used to filter data based on equality, inequality, or size. They are applicable to numeric and text fields.

### Supported Comparison Operators:

- `==` (Equal to)
- `!=` (Not equal to)
- `>` (Greater than)
- `<` (Less than)
- `>=` (Greater than or equal to)
- `<=` (Less than or equal to)

### Example 1: Filtering with Equal To ( == )

Assume you have a field named `status` and you want to find all entities where `status` is "active". You can use the equality operator `==` :

```
filter = 'status == "active"'
```

### Example 2: Filtering with Not Equal To ( != )

To find entities where `status` is not "inactive":

```
filter = 'status != "inactive"'
```

### Example 3: Filtering with Greater Than ( &gt; )

If you want to find all entities with an `age` greater than 30:

```
filter = 'age > 30'
```

### Example 4: Filtering with Less Than

To find entities where `price` is less than 100:

```
filter = 'price < 100'
```

### Example 5: Filtering with Greater Than or Equal To ( &gt;= )

If you want to find all entities with `rating` greater than or equal to 4:

```
filter = 'rating >= 4'
```

### Example 6: Filtering with Less Than or Equal To

To find entities with `discount` less than or equal to 10%:

```
filter = 'discount <= 10'
```

## Range operators

Range operators help filter data based on specific sets or ranges of values.

### Supported Range Operators:

- `LIKE` : Used to match a pattern (mostly for text fields).

### Example 1: Using LIKE for Pattern Matching

The `LIKE` operator is used for pattern matching in string fields. It can match substrings in different positions within the text: as a **prefix** , **infix** , or **suffix** . The `LIKE` operator uses the `%` symbol as a wildcard, which can match any number of characters (including zero).

In most cases, **infix** or **suffix** matching is significantly slower than prefix matching. Use them with caution if performance is critical.

### Prefix Match (Starts With)

To perform a **prefix** match, where the string starts with a given pattern, you can place the pattern at the beginning and use `%` to match any characters following it. For example, to find all products whose `name` starts with "Prod":

```
filter = 'name LIKE "Prod%"'
```

This will match any product whose name starts with "Prod", such as "Product A", "Product B", etc.

### Suffix Match (Ends With)

For a **suffix** match, where the string ends with a given pattern, place the `%` symbol at the beginning of the pattern. For example, to find all products whose `name` ends with "XYZ":

```
filter = 'name LIKE "%XYZ"'
```

This will match any product whose name ends with "XYZ", such as "ProductXYZ", "SampleXYZ", etc.

### Infix Match (Contains)

To perform an **infix** match, where the pattern can appear anywhere in the string, you can place the `%` symbol at both the beginning and the end of the pattern. For example, to find all products whose `name` contains the word "Pro":

```
filter = 'name LIKE "%Pro%"'
```

This will match any product whose name contains the substring "Pro", such as "Product", "ProLine", or "SuperPro".

## Arithmetic Operators

Arithmetic operators allow you to create conditions based on calculations involving numeric fields.

### Supported Arithmetic Operators:

- `+` (Addition)
- `-` (Subtraction)
- `*` (Multiplication)
- `/` (Division)
- `%` (Modulus)
- `**` (Exponentiation)

### Example 1: Using Modulus ( % )

To find entities where the `id` is an even number (i.e., divisible by 2):

```
filter = 'id % 2 == 0'
```

### Example 2: Using Exponentiation ( ** )

To find entities where `price` raised to the power of 2 is greater than 1000:

```
filter = 'price ** 2 > 1000'
```

## Logical Operators

Logical operators are used to combine multiple conditions into a more complex filter expression. These include `AND` , `OR` , and `NOT` .

### Supported Logical Operators:

- `AND` : Combines multiple conditions that must all be true.
- `OR` : Combines conditions where at least one must be true.
- `NOT` : Negates a condition.

### Example 1: Using AND to Combine Conditions

To find all products where `price` is greater than 100 and `stock` is greater than 50:

```
filter = 'price > 100 AND stock > 50'
```

### Example 2: Using OR to Combine Conditions

To find all products where `color` is either "red" or "blue":

```
filter = 'color == "red" OR color == "blue"'
```

### Example 3: Using NOT to Exclude a Condition

To find all products where `color` is not "green":

```
filter = 'NOT color == "green"'
```
