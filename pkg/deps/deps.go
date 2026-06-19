package deps

import (
	"github.com/mrh30000/go-rpc/pkg/config"
	"github.com/mrh30000/go-rpc/pkg/database/repository"
	"github.com/mrh30000/go-rpc/pkg/eventbus"
	"gorm.io/gorm"
)

// AppDependencies aggregates all shared dependencies for dependency injection.
// Constructed once in main.go and passed to all modules that need them.
type AppDependencies struct {
	DB            *gorm.DB
	UserRepo      repository.UserRepository
	GroupRepo     repository.GroupRepository
	ConfigService config.Service
	EventBus      *eventbus.EventBus
}
