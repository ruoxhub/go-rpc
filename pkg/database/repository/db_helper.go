package repository

import "gorm.io/gorm"

// mustDB returns db if non-nil, otherwise panics.
//
// All repository constructors in this package accept a *gorm.DB and rely on
// mustDB() as a hard-fail guard so that a forgotten injection site surfaces
// immediately at startup instead of silently falling back to the global
// database.DB singleton.
func mustDB(db *gorm.DB) *gorm.DB {
	if db == nil {
		panic("repository: *gorm.DB is nil — pass it explicitly via the New* constructor")
	}
	return db
}
