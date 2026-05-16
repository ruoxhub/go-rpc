package eventbus

import "reflect"

// funcEqual compares two function values by their pointer addresses.
// Go does not allow direct comparison of function values.
func funcEqual(a, b EventHandler) bool {
	return reflect.ValueOf(a).Pointer() == reflect.ValueOf(b).Pointer()
}
