#pragma once

// Kept as two distinct enums, even though the members mirror each other,
// per project decision: FilterType (which channel is "active") and
// ChargeType (which accumulator a charge value belongs to) are used in
// conceptually different ways throughout the Python source and are never
// meant to be interchangeable.
enum class FilterType { White, Blue, Red };
enum class ChargeType { White, Blue, Red };
