package repository

import (
	"github.com/mrh30000/go-rpc/pkg/database"
	"gorm.io/gorm"
)

// GetDB returns the global database instance.
// Used by repository implementations as a fallback when no specific DB is injected.
func GetDB() *gorm.DB {
	return database.GetDB()
}
