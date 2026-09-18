package main

import (
	"container/list"
	"sync"
)

type Entry struct {
	key   string
	value []byte
	size  int64
}

type Bucket struct {
	mu       sync.Mutex
	capacity int64
	size     int64
	items    map[string]*list.Element
	lru      *list.List
}

type Store struct {
	buckets map[string]*Bucket
}

func newStore(config map[string]int64) *Store {
	store := &Store{buckets: map[string]*Bucket{}}

	for name, capacity := range config {
		store.buckets[name] = &Bucket{
			capacity: capacity,
			items:    map[string]*list.Element{},
			lru:      list.New(),
		}
	}

	return store
}

func (s *Store) bucket(name string) *Bucket {
	return s.buckets[name]
}

func (b *Bucket) get(key string) ([]byte, bool) {
	b.mu.Lock()

	defer b.mu.Unlock()

	element, found := b.items[key]

	if !found {
		return nil, false
	}

	b.lru.MoveToFront(element)

	return element.Value.(*Entry).value, true
}

func (b *Bucket) put(key string, value []byte) bool {
	size := int64(len(key)) + int64(len(value))

	if size > b.capacity {
		return false
	}

	b.mu.Lock()

	defer b.mu.Unlock()

	if element, found := b.items[key]; found {
		entry := element.Value.(*Entry)

		b.size -= entry.size
		entry.value = value
		entry.size = size
		b.size += size
		b.lru.MoveToFront(element)
	} else {
		entry := &Entry{key: key, value: value, size: size}
		element := b.lru.PushFront(entry)

		b.items[key] = element
		b.size += size
	}

	for b.size > b.capacity {
		b.remove(b.lru.Back())
	}

	return true
}

func (b *Bucket) remove(element *list.Element) {
	entry := element.Value.(*Entry)

	delete(b.items, entry.key)
	b.lru.Remove(element)
	b.size -= entry.size
}
